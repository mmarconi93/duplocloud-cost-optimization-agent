import os
import datetime
from typing import Dict, Any, List, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def detect_anomalies(lookback_days: int = 90, z: float = 3.0, window: int = 7) -> Dict[str, Any]:
    """
    Naive z-score anomaly detection over daily UnblendedCost totals.
    Uses Cost Explorer; end date is exclusive (AWS behavior).
    """
    region = os.getenv("AWS_REGION", "us-east-1")
    ce = boto3.client("ce", region_name=region)

    end = datetime.date.today() + datetime.timedelta(days=1)  # CE end is exclusive
    start = end - datetime.timedelta(days=lookback_days)

    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": str(start), "End": str(end)},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        # If CE isn’t enabled/ingested yet, return a clean message
        if code == "DataUnavailableException":
            return {
                "lookbackDays": lookback_days,
                "z": z,
                "window": window,
                "anomalies": [],
                "note": "Cost Explorer data is not available yet (DataUnavailableException).",
            }
        return {"lookbackDays": lookback_days, "z": z, "window": window, "anomalies": [], "note": str(e)}
    except BotoCoreError as e:
        return {"lookbackDays": lookback_days, "z": z, "window": window, "anomalies": [], "note": str(e)}

    series: List[Tuple[str, float]] = []
    for day in resp.get("ResultsByTime", []) or []:
        amt = float(day["Total"]["UnblendedCost"]["Amount"])
        series.append((day["TimePeriod"]["Start"], amt))

    vals = [v for _, v in series]
    anomalies = []
    for i, (ts, v) in enumerate(series):
        if i < window:
            continue
        hist = vals[i - window : i]
        mean = sum(hist) / window
        var = sum((x - mean) ** 2 for x in hist) / window
        std = var ** 0.5
        score = (v - mean) / std if std > 0 else 0.0
        if score >= z:
            anomalies.append({"date": ts, "amount": v, "z": round(score, 2)})

    return {"lookbackDays": lookback_days, "z": z, "window": window, "anomalies": anomalies}