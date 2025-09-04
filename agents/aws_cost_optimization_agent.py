from typing import Dict, Any, List, Optional, Callable
import os, re, json, logging
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

from agent_server import AgentProtocol
from schemas.messages import AgentMessage

# Local (fallback) tools when not using MCP
from tools.cost_explorer import get_cost_summary
from tools.compute_optimizer import get_ec2_rightsizing
from tools.idle_assets import find_idle_assets

# MCP proxy invoker
from services.mcp_client import invoke as mcp_invoke

logger = logging.getLogger(__name__)

HELP_EXAMPLES = [
    "cost summary",
    "rightsizing recommendations",
    "idle assets",
    "mcp ce ping",
    "mcp pricing ping",
    "mcp bcm ping",
]

HELP_MD = (
    "### I can help with AWS cost optimization\n"
    "Try one of these:\n"
    + "".join([f"- `{ex}`\n" for ex in HELP_EXAMPLES])
    + "\nYou can also say `/help` at any time."
)

# Canonical “intents” we support.
CANONICAL = {
    "cost summary": "cost summary",
    "rightsizing recommendations": "rightsizing",
    "idle assets": "idle",
}

QUICK_START = [
    "idle assets",
    "rightsizing recommendations",
    "cost summary",
]

def build_quick_replies(examples: List[str]) -> List[Dict[str, str]]:
    """Return UI-friendly quick replies (chips/buttons) the HelpDesk can render."""
    return [{"title": ex, "payload": ex} for ex in examples]

def _render_unknown(query: str) -> AgentMessage:
    keys = list(CANONICAL.keys())
    guess = get_close_matches(query.lower().strip(), keys, n=1, cutoff=0.6)
    hint = f"Did you mean **{guess[0]}**?" if guess else "I didn’t quite catch that."

    return AgentMessage(
        content=f"{hint}\n\n{HELP_MD}",
        data={
            "suggestions": HELP_EXAMPLES,               # keep for older UIs
            "quick_replies": build_quick_replies(QUICK_START),
        },
    )

def _ymd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def _safe(
    fn: Callable[[], Any],
    *,
    label: str,
    default_msg: str,
    post: Optional[Callable[[Any], AgentMessage]] = None,
) -> AgentMessage:
    """Run a callable and return an AgentMessage, guarding exceptions."""
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

def _fmt_rows(rows: List[Dict[str, Any]], cols: List[tuple[str, Any]]) -> str:
    """
    Render a compact, monospace table from a list of dicts.
    cols: [(header, key_in_row_or_callable)]
    """
    # Resolve values
    data: List[List[str]] = []
    for r in rows:
        out_row: List[str] = []
        for _header, key in cols:
            if callable(key):
                out_row.append(str(key(r)))
            else:
                out_row.append(str(r.get(key, "")))
        data.append(out_row)

    # Compute widths
    headers = [h for h, _ in cols]
    widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(row: List[str]) -> str:
        return "  " + "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    lines = []
    lines.append(fmt_row(headers))
    lines.append(fmt_row(["-" * w for w in widths]))
    for row in data[:15]:  # keep it tidy; show first 15
        lines.append(fmt_row(row))
    if len(data) > 15:
        lines.append(f"  ... and {len(data) - 15} more")
    return "\n".join(lines)

# --------- Post-formatters ---------

def _post_cost_summary(result: Dict[str, Any], lookback_days: int) -> AgentMessage:
    """
    Expecting a dict shaped like:
      {
        "narrative": "text...",          # optional
        "total": 123.45,                 # optional
        "currency": "USD",               # optional
        "top": [ ["Amazon EC2", 45.2], ["Amazon S3", 17.9], ... ],  # optional
        "notes": ["..."]                 # optional
      }
    Fallbacks gracefully if some keys are missing.
    """
    narrative = result.get("narrative") or f"Cost summary (last {lookback_days}d)."

    lines: List[str] = [f"### {narrative}"]

    total = result.get("total")
    currency = result.get("currency", "USD")
    if isinstance(total, (int, float)):
        lines.append(f"\n**Total**: {total:.2f} {currency}")

    top = result.get("top") or []
    if isinstance(top, list) and top:
        # Render a compact table of top services/tags
        rows = [{"k": k, "v": v} for k, v in top[:10]]
        lines.append("\n**Top cost drivers**")
        lines.append(_fmt_rows(rows, [
            ("Key", "k"),
            (f"Spend ({currency})", lambda r: f"{float(r.get('v', 0)):.2f}"),
        ]))

    # Friendly next steps
    recs: List[str] = []
    if isinstance(total, (int, float)) and total > 0:
        recs.append("Create a monthly budget and alert thresholds at 80/90/100%.")
    if top:
        recs.append("Review top services/tags and check tag hygiene (Owner, Environment).")
    recs.append("Look for idle assets and rightsizing opportunities.")

    lines.append("\n**Recommendations**\n- " + "\n- ".join(recs))

    # Optional notes (e.g., permission or data availability hints)
    notes = result.get("notes") or []
    if notes:
        lines.append("\n**Notes**\n- " + "\n- ".join(notes))

    body = "\n".join(lines).strip()

    quick = [
        {"title": "Idle assets", "payload": "idle assets"},
        {"title": "Rightsizing recommendations", "payload": "rightsizing recommendations"},
    ]
    return AgentMessage(content=body, data={"quick_replies": quick})

def _post_rightsizing(result: Dict[str, Any], iam_role_name: Optional[str] = None) -> AgentMessage:
    note = (result or {}).get("note", "") or ""
    items = result.get("items") or []
    count = int(result.get("count") or 0)

    # Handle missing permissions clearly
    if "AccessDenied" in note or "not authorized" in note:
        role_hint = f" (`{iam_role_name}`)" if iam_role_name else ""
        body = (
            "### Compute Optimizer access needed\n"
            f"This agent{role_hint} doesn’t have permission to read Compute Optimizer recommendations.\n\n"
            "**How to fix**\n"
            "- Attach an IAM policy that allows `compute-optimizer:GetEC2InstanceRecommendations` to the IRSA role used by the **mcp-proxy** (or the agent if calling directly).\n"
            "- Ensure **Compute Optimizer is opted-in** for the account/region.\n\n"
            "**Quick check**\n"
            "```bash\n"
            "aws compute-optimizer get-enrollment-status --region $AWS_REGION\n"
            "```\n"
        )
        return AgentMessage(
            content=body,
            data={
                "quick_replies": [
                    {"title": "Idle assets", "payload": "idle assets"},
                    {"title": "Cost summary", "payload": "cost summary"},
                ]
            },
        )

    # No items but no error: be explicit
    if count == 0 or not items:
        body = (
            "### Rightsizing recommendations\n"
            "No EC2 rightsizing opportunities were found right now. ✅\n\n"
            "**Tips**\n"
            "- Verify workload hours (consider schedules for non-prod).\n"
            "- Confirm CPU/Memory over 14–30 days before downsizing.\n"
            "- Track tag hygiene (Owner, Environment) for accountability.\n"
        )
        return AgentMessage(
            content=body,
            data={"quick_replies": [
                {"title": "Idle assets", "payload": "idle assets"},
                {"title": "Cost summary", "payload": "cost summary"},
            ]},
        )

    # We have recommendations: show a compact table + next steps
    table = _fmt_rows(
        items[:15],
        [
            ("InstanceId",  lambda r: r.get("instanceId") or r.get("instanceArn", "")[-12:]),
            ("CurrentType", "currentType"),
            ("TopRec",      lambda r: (r.get("recommendations") or ["—"])[0]),
            ("Est$/mo",     lambda r: (r.get("estimatedMonthlySavings") or {}).get("amount") or "—"),
        ],
    )

    body = (
        f"### Rightsizing recommendations ({count})\n\n"
        f"{table}\n\n"
        "**Next steps**\n"
        "- Apply CO recommendations to top candidates.\n"
        "- Schedule non-prod instances to stop outside business hours.\n"
        "- Validate performance (CPU/Memory, p95) over 14–30 days before downsizing.\n"
    )
    return AgentMessage(
        content=body,
        data={"quick_replies": [
            {"title": "Idle assets", "payload": "idle assets"},
            {"title": "Cost summary", "payload": "cost summary"},
        ]},
    )

def _post_idle_assets(result: Dict[str, Any]) -> AgentMessage:
    vols = result.get("unattachedVolumes") or []
    eips = result.get("unassociatedEIPs") or []
    low  = result.get("lowUtilizationInstances") or []
    lookback = result.get("lookbackDays", 14)
    cpu_thr  = result.get("cpuThreshold", 5.0)

    sections: List[str] = []
    sections.append(f"**Idle / Orphaned Assets** (lookback: {lookback}d, CPU < {cpu_thr}%)")

    # Instances
    if low:
        sections.append(f"\n**Low-CPU EC2 instances** ({len(low)})")
        sections.append(_fmt_rows(
            low,
            [
                ("InstanceId", "instanceId"),
                ("Type", "type"),
                ("AvgCPU%", lambda r: f"{r.get('avgCPU', 0):.2f}"),
            ],
        ))
        sections.append(
            "\nNext steps:\n"
            f"- Stop or downsize non-prod instances below {cpu_thr}% avg CPU.\n"
            "- For prod, consider rightsizing after verifying 14–30 days of metrics.\n"
            "- Tag owners (e.g., `Owner`, `Environment`) and set budgets/alerts.\n"
        )
    else:
        sections.append("\n**Low-CPU EC2 instances**: none found ✅")

    # Unattached EBS
    if vols:
        sections.append(f"\n**Unattached EBS volumes** ({len(vols)})")
        sections.append(_fmt_rows(
            vols,
            [
                ("VolumeId", "volumeId"),
                ("SizeGiB", "sizeGiB"),
                ("AZ",       "az"),
                ("Created",  "createTime"),
            ],
        ))
        sections.append(
            "\nNext steps:\n"
            "- Snapshot, set a short retention, then delete to save cost.\n"
        )
    else:
        sections.append("\n**Unattached EBS volumes**: none found ✅")

    # Unassociated EIPs
    if eips:
        sections.append(f"\n**Unassociated Elastic IPs** ({len(eips)})")
        sections.append("  " + ", ".join(eips[:20]) + (f" … +{len(eips)-20} more" if len(eips) > 20 else ""))
        sections.append("\nNext steps:\n- Release unused EIPs to avoid hourly charges.\n")
    else:
        sections.append("\n**Unassociated Elastic IPs**: none found ✅")

    body = "\n".join(sections).strip()

    # Handy follow-ups
    quick_replies = [
        {"title": "Rightsizing recommendations", "payload": "rightsizing recommendations"},
        {"title": "Cost summary", "payload": "cost summary"},
    ]

    return AgentMessage(
        content=body,
        data={
            "quick_replies": quick_replies,
            "suggestions": [qr["payload"] for qr in quick_replies],  # legacy hint
        },
    )

# --------------------------------------------------------------------
# Helpers for MCP error extraction and friendly mapping
# --------------------------------------------------------------------

def _extract_ce_error(resp: Dict[str, Any]) -> Optional[str]:
    """Try to pull a CE error message from several possible shapes returned by the MCP proxy."""
    # direct form
    err = (resp or {}).get("error") or (resp or {}).get("message")
    if err:
        return err
    # structuredContent.result.error
    sc = (resp or {}).get("structuredContent") or {}
    if isinstance(sc, dict):
        r = sc.get("result") or {}
        if isinstance(r, dict):
            e = r.get("error")
            if e:
                return e
    # result.error
    r = (resp or {}).get("result") or {}
    if isinstance(r, dict):
        e = r.get("error")
        if e:
            return e
    # content array with one text blob that contains an error line
    content = (resp or {}).get("content") or []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                t = item.get("text") or ""
                if "Exception" in t or "not authorized" in t:
                    return t
    return None

def _map_ce_error_to_summary(err: str, iam_role_name: Optional[str]) -> Dict[str, Any]:
    """Turn a raw CE error into a friendly summary dict our post-formatter can render."""
    role_hint = f" (`{iam_role_name}`)" if iam_role_name else ""
    notes: List[str] = []

    if "AccessDeniedException" in err or "not authorized" in err:
        notes.append(
            "Insufficient permissions for Cost Explorer. "
            "Attach **AWSCostExplorerReadOnlyAccess** to the IRSA role"
            f"{role_hint} and retry."
        )
        return {
            "narrative": "Cost summary unavailable (permissions).",
            "total": 0,
            "top": [],
            "notes": notes,
        }

    if "DataUnavailableException" in err:
        notes.append(
            "Cost Explorer data isn’t available yet. After enabling Cost Explorer, "
            "ingestion can take up to ~24h."
        )
        return {
            "narrative": "Cost summary unavailable (data not ready).",
            "total": 0,
            "top": [],
            "notes": notes,
        }

    # generic
    notes.append(f"Cost Explorer error: {err}")
    return {
        "narrative": "Cost summary unavailable (error).",
        "total": 0,
        "top": [],
        "notes": notes,
    }

# --------------------------------------------------------------------
def _try_parse_json_text_blob(resp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    If MCP wrapped CE output as a text blob that itself is JSON, parse and return it.
    Handles shapes like resp["content"][0]["text"] or resp["last"]["result"]["content"][0]["text"].
    """
    def _get_text_blobs(node) -> List[str]:
        blobs = []
        content = (node or {}).get("content") or []
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    t = item.get("text")
                    if isinstance(t, str) and t.strip():
                        blobs.append(t)
        return blobs

    # Direct shape
    for t in _get_text_blobs(resp or {}):
        try:
            return json.loads(t)
        except Exception:
            pass

    # frames/last shape (like your HelpDesk “raw_lines” example)
    last = (resp or {}).get("last") or {}
    for t in _get_text_blobs(last.get("result") or {}):
        try:
            return json.loads(t)
        except Exception:
            pass

    return None


def _unwrap_mcp_result(resp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize various MCP result envelopes to a single dict:
      - If 'last' exists, use last['result']
      - Else if 'result' exists, use it
      - Else if top-level has 'meta'+'content', treat it as the result
      - Else try parsing a JSON text blob inside 'content'
    """
    if not isinstance(resp, dict):
        return {}

    if "last" in resp and isinstance(resp["last"], dict) and "result" in resp["last"]:
        inner = resp["last"]["result"]
        return inner if isinstance(inner, dict) else {}

    if "result" in resp and isinstance(resp["result"], dict):
        return resp["result"]

    # Result-like object
    if "meta" in resp and "content" in resp:
        return resp

    # Parse nested JSON text (common when MCP servers emit a JSON string)
    parsed = _try_parse_json_text_blob(resp)
    if isinstance(parsed, dict):
        return parsed

    return resp


def _normalize_ce_response_to_summary(resp: Dict[str, Any],
                                      lookback_days: int,
                                      iam_role_name: Optional[str]) -> Dict[str, Any]:
    """
    Turn raw CE output (as returned by AWS Cost Explorer API via MCP) into a summary dict:
      { narrative, total, currency, top: [(key, amount), ...], notes? }
    Also maps common errors to friendly “notes”.
    """
    # 1) unwrap odd envelopes first
    inner = _unwrap_mcp_result(resp)

    # 2) check for explicit error fields and map nicely
    err = _extract_ce_error(inner) or _extract_ce_error(resp)
    if err:
        return _map_ce_error_to_summary(err, iam_role_name)

    # 3) If the server already returned a summary-ish object, just pass it through
    if any(k in inner for k in ("total", "top", "narrative")):
        return inner

    # 4) Otherwise, try to summarize a *raw* AWS CE GetCostAndUsage payload
    # Expected raw keys: ResultsByTime[], Dimension/Group structure, etc.
    results = (inner or {}).get("ResultsByTime") or (inner or {}).get("resultsByTime")
    if not isinstance(results, list) or not results:
        # Nothing we can summarize — return a friendly placeholder
        return {
            "narrative": f"Cost summary (last {lookback_days}d).",
            "total": 0,
            "currency": "USD",
            "top": [],
            "notes": ["No Cost Explorer data found in the response."],
        }

    currency = "USD"
    total_amount = 0.0
    by_key: Dict[str, float] = {}

    for rb in results:
        groups = rb.get("Groups") or rb.get("groups") or []
        # When grouped (e.g., SERVICE or TAG)
        if groups:
            for g in groups:
                keys = g.get("Keys") or g.get("keys") or []
                k = keys[0] if keys else "Other"
                metrics = g.get("Metrics") or g.get("metrics") or {}
                uc = metrics.get("UnblendedCost") or metrics.get("unblendedCost") or {}
                amount = uc.get("Amount") or uc.get("amount") or "0"
                unit = uc.get("Unit") or uc.get("unit") or currency
                try:
                    val = float(amount)
                except Exception:
                    val = 0.0
                currency = unit or currency
                total_amount += val
                by_key[k] = by_key.get(k, 0.0) + val
        else:
            # Ungrouped totals
            total = (rb.get("Total") or rb.get("total") or {}).get("UnblendedCost") or {}
            amount = total.get("Amount") or "0"
            unit = total.get("Unit") or currency
            try:
                val = float(amount)
            except Exception:
                val = 0.0
            currency = unit or currency
            total_amount += val

    # Build top list
    top: List[tuple[str, float]] = []
    if by_key:
        top = sorted(by_key.items(), key=lambda kv: kv[1], reverse=True)[:10]

    return {
        "narrative": f"Cost summary (last {lookback_days}d).",
        "total": round(total_amount, 2),
        "currency": currency or "USD",
        "top": top,
    }

class CostOptimizationAgent(AgentProtocol):
    def invoke(self, payload: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        msgs = payload.get("messages", [])
        user = next((m for m in reversed(msgs) if m.get("role") == "user"), {})
        text_raw: str = user.get("content") or ""
        text_lc = text_raw.lower().strip()

        platform_ctx = user.get("platform_context") or {}
        iam_role_name = platform_ctx.get("aws_iam_role_name")

        # Quick help
        if text_lc in ("/help", "help", "what can you do", "commands"):
            return AgentMessage(
                content=HELP_MD,
                data={
                    "suggestions": HELP_EXAMPLES,
                    "quick_replies": build_quick_replies(QUICK_START),
                },
            )

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
                today = datetime.now(timezone.utc).date()
                start = today - timedelta(days=lookback_days)
                params: Dict[str, Any] = {
                    "date_range": {"start_date": _ymd(start), "end_date": _ymd(today)},
                    "granularity": "DAILY",
                    "metric": "UnblendedCost",
                }
                if group_by == "TAG" and tag_key:
                    params["group_by"] = {"Type": "TAG", "Key": tag_key}
                else:
                    params["group_by"] = "SERVICE"

                def _call():
                    raw = mcp_invoke("ce", {"tool": "get_cost_and_usage", "params": params})
                    # Normalize any shape (success or error) into a friendly summary dict
                    return _normalize_ce_response_to_summary(raw, lookback_days, iam_role_name)

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
            return _safe(
                _call,
                label="rightsizing",
                default_msg="Rightsizing analysis ready.",
                post=lambda r: _post_rightsizing(r, iam_role_name=iam_role_name),
            )

        if "idle" in text_lc or "orphan" in text_lc:
            def _call():
                return find_idle_assets(lookback_days=14, cpu_threshold=5.0)
            return _safe(_call, label="idle asset scan", default_msg="Idle/orphaned assets report ready.", post=_post_idle_assets)

        if "mcp ce ping" in text_lc:
            return _safe(lambda: mcp_invoke("ce", {"ping": True}),
                         label="mcp ce ping", default_msg="MCP CE responded.")
        if "mcp pricing ping" in text_lc:
            return _safe(lambda: mcp_invoke("pricing", {"ping": True}),
                         label="mcp pricing ping", default_msg="MCP Pricing responded.")
        if "mcp bcm ping" in text_lc:
            return _safe(lambda: mcp_invoke("bcm", {"ping": True}),
                         label="mcp bcm ping", default_msg="MCP Billing & Cost Mgmt responded.")

        # --- graceful fallback ---
        return _render_unknown(text_raw)