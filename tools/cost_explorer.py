import os
import datetime
from typing import Dict, List, Tuple, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def _region() -> str:
    return os.getenv("AWS_REGION", "us-east-1")


def get_cost_summary(
    lookback_days: int = 30,
    group_by: str = "SERVICE",
    tag_key: Optional[str] = None,
) -> Dict[str, any]:
    """
    Roll-up summary for the lookback window, optionally grouped by SERVICE or TAG:<key>.
    CE end date is exclusive; we +1 day to include 'today'.
    """
    ce = boto3.client("ce", region_name=_region())
    end = datetime.date.today() + datetime.timedelta(days=1)  # CE end is exclusive
    start = end - datetime.timedelta(days=lookback_days)

    if group_by == "SERVICE":
        group_defs = [{"Type": "DIMENSION", "Key": "SERVICE"}]
    else:
        group_defs = [{"Type": "TAG", "Key": (tag_key or "Environment")}]

    groups_totals: Dict[str, float] = {}
    next_token: Optional[str] = None

    try:
        while True:
            kwargs = dict(
                TimePeriod={"Start": str(start), "End": str(end)},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
                GroupBy=group_defs,
                # You can choose to exclude Credits/Refunds; here we keep it simple
            )
            if next_token:
                kwargs["NextPageToken"] = next_token

            resp = ce.get_cost_and_usage(**kwargs)

            for day in resp.get("ResultsByTime", []) or []:
                for g in day.get("Groups", []) or []:
                    key = g["Keys"][0]
                    amt = float(g["Metrics"]["UnblendedCost"]["Amount"])
                    groups_totals[key] = groups_totals.get(key, 0.0) + amt

            next_token = resp.get("NextPageToken")
            if not next_token:
                break

    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "DataUnavailableException":
            # Surface a friendly payload (agent post-formatter already handles this)
            return {
                "total": 0.0,
                "top": [],
                "narrative": (
                    "Cost Explorer data isn’t available in this account yet. "
                    "After enabling Cost Explorer, it can take up to ~24h to ingest."
                ),
                "group_by": group_by,
                "tag_key": tag_key,
                "error": "DataUnavailableException",
            }
        # Any other CE error
        return {
            "total": 0.0,
            "top": [],
            "narrative": "Failed to retrieve Cost Explorer data.",
            "group_by": group_by,
            "tag_key": tag_key,
            "error": str(e),
        }
    except BotoCoreError as e:
        return {
            "total": 0.0,
            "top": [],
            "narrative": "Failed to reach Cost Explorer.",
            "group_by": group_by,
            "tag_key": tag_key,
            "error": str(e),
        }

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

    Behavior:
    - Raises ClientError(DataUnavailableException) so the caller (charts/API)
      can return a 503/204 appropriately.
    - For other exceptions (e.g., dev without creds), returns a deterministic
      synthetic series to keep UIs usable.
    """
    end = datetime.date.today() + datetime.timedelta(days=1)  # CE end is exclusive
    start = end - datetime.timedelta(days=lookback_days)

    ce = boto3.client("ce", region_name=_region())
    series: List[Tuple[datetime.date, float]] = []
    next_token: Optional[str] = None

    try:
        while True:
            kwargs = dict(
                TimePeriod={"Start": str(start), "End": str(end)},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )
            if next_token:
                kwargs["NextPageToken"] = next_token

            resp = ce.get_cost_and_usage(**kwargs)
            for day in resp.get("ResultsByTime", []) or []:
                d = datetime.date.fromisoformat(day["TimePeriod"]["Start"])
                amt = float(day["Total"]["UnblendedCost"]["Amount"])
                series.append((d, amt))

            next_token = resp.get("NextPageToken")
            if not next_token:
                break

        series.sort(key=lambda t: t[0])
        return series

    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "DataUnavailableException":
            # Let API layer map this to 503/204
            raise
        # Fall through to synthetic for other CE client errors
    except BotoCoreError:
        pass

    # Fallback: deterministic synthetic ramp for local testing / no creds
    base = datetime.date.today() - datetime.timedelta(days=lookback_days - 1)
    return [(base + datetime.timedelta(days=i), round(0.5 * (i + 1), 2)) for i in range(lookback_days)]