from typing import Dict, Any, List, Optional, Callable
import os, re, json, logging

from agent_server import AgentProtocol
from schemas.messages import AgentMessage
from tools.cost_explorer import get_cost_summary
from tools.compute_optimizer import get_ec2_rightsizing
from tools.idle_assets import find_idle_assets
from tools.cost_anomaly import detect_anomalies
from services.mcp_client import invoke as mcp_invoke

logger = logging.getLogger(__name__)

HELP = (
    "Try: 'cost summary last 30 days by service', "
    "'cost summary last 7 days tag:Environment', "
    "'rightsizing recommendations', or 'idle assets'."
)

def _safe(
    fn: Callable[[], Any],
    *,
    label: str,
    default_msg: str,
    post: Optional[Callable[[Any], AgentMessage]] = None,
) -> AgentMessage:
    """Run a callable and return an AgentMessage, guarding exceptions.
    If `post` is provided, it will format the result into an AgentMessage.
    """
    try:
        result = fn()
        if post is not None:
            return post(result)
        if isinstance(result, dict):
            return AgentMessage(content=f"{default_msg}\n\n{json.dumps(result, indent=2)}")
        return AgentMessage(content=default_msg)
    except Exception as e:
        logger.exception("Error in %s", label)
        return AgentMessage(content=f"Sorry, {label} failed: {e}")

# --------- Post-formatters to add actionable recommendations ---------

def _post_cost_summary(result: Dict[str, Any], lookback_days: int) -> AgentMessage:
    narrative = result.get("narrative") or f"Cost summary (last {lookback_days}d)."
    recs: List[str] = []
    top = result.get("top") or []
    if isinstance(top, list) and top:
        for k, _v in top[:2]:
            recs.append(f"Review {k} cost drivers; consider tagging hygiene, budgets, and rightsizing.")
    total = result.get("total")
    if isinstance(total, (int, float)) and total > 0:
        recs.append("Create a budget + alert at 80/90/100% of expected monthly spend.")
    # Link to a PNG chart endpoint if added
    chart_hint = f"\nView trend: /charts/cost-trend.png?lookback_days={lookback_days}"

    body = narrative
    if recs:
        body += "\n\nRecommendations:\n- " + "\n- ".join(recs)
    body += chart_hint
    body += "\n\n" + json.dumps(result, indent=2)
    return AgentMessage(content=body)

def _post_rightsizing(result: Dict[str, Any]) -> AgentMessage:
    count = result.get("count", 0)
    items = result.get("items") or []
    sample = []
    for it in items[:3]:
        inst = it.get("instanceArn") or it.get("instanceId") or "instance"
        recs = it.get("recommendations") or []
        if recs:
            sample.append(f"{inst} → {recs[0]} (candidate)")
    recs_txt = (
        "- Apply Compute Optimizer recommendations to top candidates.\n"
        "- Schedule non-prod instances to stop outside business hours.\n"
        "- Verify CPU/Memory metrics for at least 14 days before downsizing."
    )
    body = f"Found {count} EC2 rightsizing opportunities."
    if sample:
        body += "\nExamples:\n- " + "\n- ".join(sample)
    body += "\n\nRecommendations:\n" + recs_txt
    body += "\n\n" + json.dumps(result, indent=2)
    return AgentMessage(content=body)

def _post_idle_assets(result: Dict[str, Any]) -> AgentMessage:
    vols = result.get("unattachedVolumes") or []
    eips = result.get("unassociatedEIPs") or []
    low  = result.get("lowUtilizationInstances") or []
    body = "Idle/orphaned assets report."
    bullets = []
    if vols:
        bullets.append(f"{len(vols)} unattached EBS volumes — snapshot then delete to save costs.")
    if eips:
        bullets.append(f"{len(eips)} unassociated Elastic IPs — release to avoid charges.")
    if low:
        bullets.append(f"{len(low)} low-CPU EC2 instances — consider stop/resize if <5% for 14d.")
    if bullets:
        body += "\n\nRecommendations:\n- " + "\n- ".join(bullets)
    body += "\n\n" + json.dumps(result, indent=2)
    return AgentMessage(content=body)

def _post_anomalies(result: Dict[str, Any]) -> AgentMessage:
    anomalies = result.get("anomalies") or []
    body = f"Anomaly analysis: {len(anomalies)} potential anomalies detected."
    tips = (
        "- Set up Cost Anomaly Detection monitors and SNS alerts.\n"
        "- Correlate spikes with deployments, new services, or data transfer."
    )
    body += "\n\nRecommendations:\n" + tips
    body += "\n\n" + json.dumps(result, indent=2)
    return AgentMessage(content=body)

# --------------------------------------------------------------------

class CostOptimizationAgent(AgentProtocol):
    def invoke(self, payload: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        msgs = payload.get("messages", [])
        user = next((m for m in reversed(msgs) if m.get("role") == "user"), {})
        text_raw: str = user.get("content") or ""
        text_lc = text_raw.lower()

        # ---- MVP parsing ----
        lookback_days = 30
        m = re.search(r"last\s+(\d{1,3})\s*days", text_lc)
        if m:
            try:
                lookback_days = max(1, min(365, int(m.group(1))))
            except ValueError:
                pass

        group_by = "SERVICE"
        tag_key: Optional[str] = None
        m = re.search(r"tag:([A-Za-z0-9_\-./]+)", text_raw, flags=re.IGNORECASE)
        if m:
            group_by = "TAG"
            tag_key = m.group(1)

        # ---- Routing ----
        use_mcp = os.getenv("AGENT_USE_MCP", "0") == "1"

        if "cost summary" in text_lc:
            if use_mcp:
                params: Dict[str, Any] = {"granularity": "DAILY", "days": lookback_days}
                if group_by == "TAG" and tag_key:
                    params["groupBy"] = {"type": "TAG", "key": tag_key}
                elif group_by == "SERVICE":
                    params["groupBy"] = {"type": "DIMENSION", "key": "SERVICE"}

                def _call():
                    # 'ce' maps to the Cost Explorer MCP server in the proxy
                    return mcp_invoke("ce", {"tool": "GetCostAndUsage", "params": params})
                return _safe(
                    _call,
                    label="cost summary (MCP CE)",
                    default_msg="Cost summary (via MCP) ready.",
                    post=lambda r: _post_cost_summary(r, lookback_days),
                )
            else:
                def _call():
                    return get_cost_summary(lookback_days=lookback_days, group_by=group_by, tag_key=tag_key)
                return _safe(
                    _call,
                    label="cost summary",
                    default_msg="Cost summary ready.",
                    post=lambda r: _post_cost_summary(r, lookback_days),
                )

        if "rightsizing" in text_lc or "compute optimizer" in text_lc:
            def _call():
                return get_ec2_rightsizing()
            return _safe(_call, label="rightsizing", default_msg="Rightsizing analysis ready.", post=_post_rightsizing)

        if "idle" in text_lc or "orphan" in text_lc:
            def _call():
                return find_idle_assets(lookback_days=14, cpu_threshold=5.0)
            return _safe(_call, label="idle asset scan", default_msg="Idle/orphaned assets report ready.", post=_post_idle_assets)

        if "anomal" in text_lc or "spend spike" in text_lc:
            def _call():
                return detect_anomalies(lookback_days=90, z=3.0)
            return _safe(_call, label="anomaly detection", default_msg="Anomaly analysis:", post=_post_anomalies)

        if "mcp ce ping" in text_lc:
            def _call():
                return mcp_invoke("ce", {"ping": True})
            return _safe(_call, label="mcp ce ping", default_msg="MCP CE responded.")

        return AgentMessage(content=HELP)