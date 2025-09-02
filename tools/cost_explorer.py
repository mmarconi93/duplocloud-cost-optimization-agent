import os
import boto3
import datetime
from typing import Dict, List, Tuple, Optional


def _region() -> str:
    return os.getenv("AWS_REGION", "us-east-1")


def get_cost_summary(lookback_days: int = 30,
                     group_by: str = "SERVICE",
                     tag_key: Optional[str] = None) -> Dict:
    """
    Returns a roll-up summary for the lookback window, optionally grouped by SERVICE or TAG:<key>.
    """
    ce = boto3.client("ce", region_name=_region())
    # CE end is exclusive; add a day so 'today' is included
    end = datetime.date.today() + datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=lookback_days)

    if group_by == "SERVICE":
        group_defs = [{"Type": "DIMENSION", "Key": "SERVICE"}]
    else:
        group_defs = [{"Type": "TAG", "Key": (tag_key or "Environment")}]

    groups_totals: Dict[str, float] = {}
    next_token: Optional[str] = None

    while True:
        kwargs = dict(
            TimePeriod={"Start": str(start), "End": str(end)},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=group_defs,
        )
        if next_token:
            kwargs["NextPageToken"] = next_token

        resp = ce.get_cost_and_usage(**kwargs)

        for day in resp.get("ResultsByTime", []):
            for g in day.get("Groups", []):
                key = g["Keys"][0]
                amt = float(g["Metrics"]["UnblendedCost"]["Amount"])
                groups_totals[key] = groups_totals.get(key, 0.0) + amt

        next_token = resp.get("NextPageToken")
        if not next_token:
            break

    top = sorted(groups_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    total = sum(groups_totals.values())
    if top:
        narrative = (
            f"Last {lookback_days}d total: ${total:,.2f}. Top drivers: "
            + ", ".join([f"{k} ${v:,.2f}" for k, v in top])
        )
    else:
        narrative = f"Last {lookback_days}d total: ${total:,.2f}."
    return {
        "total": total,
        "top": top,
        "narrative": narrative,
        "group_by": group_by,
        "tag_key": tag_key,
    }


def get_daily_series(lookback_days: int = 30) -> List[Tuple[datetime.date, float]]:
    """
    Returns a daily total series for the last N days as [(date, amount), ...].
    If AWS CE is unreachable (e.g., local dev without creds), returns a deterministic synthetic series.
    """
    end = datetime.date.today() + datetime.timedelta(days=1)   # CE end is exclusive
    start = end - datetime.timedelta(days=lookback_days)

    try:
        ce = boto3.client("ce", region_name=_region())
        series: List[Tuple[datetime.date, float]] = []
        next_token: Optional[str] = None

        while True:
            kwargs = dict(
                TimePeriod={"Start": str(start), "End": str(end)},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )
            if next_token:
                kwargs["NextPageToken"] = next_token

            resp = ce.get_cost_and_usage(**kwargs)
            for day in resp.get("ResultsByTime", []):
                # CE returns e.g. {'TimePeriod': {'Start': '2025-08-27', 'End': '2025-08-28'}, ...}
                d = datetime.date.fromisoformat(day["TimePeriod"]["Start"])
                amt = float(day["Total"]["UnblendedCost"]["Amount"])
                series.append((d, amt))

            next_token = resp.get("NextPageToken")
            if not next_token:
                break

        # Should already be chronological, but sort just in case:
        series.sort(key=lambda t: t[0])
        return series

    except Exception:
        # Fallback: deterministic synthetic ramp for local testing without creds
        base = datetime.date.today() - datetime.timedelta(days=lookback_days - 1)
        return [(base + datetime.timedelta(days=i), round(0.5 * (i + 1), 2))
                for i in range(lookback_days)]