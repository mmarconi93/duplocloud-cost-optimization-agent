import os
import datetime
import boto3

def detect_anomalies(lookback_days=90, z=3.0, window=7):
    ce = boto3.client("ce", region_name=os.getenv("AWS_REGION", "us-east-1"))
    end = datetime.date.today() + datetime.timedelta(days=1)  # CE end is exclusive
    start = end - datetime.timedelta(days=lookback_days)

    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": str(start), "End": str(end)},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )
    series = []
    for day in resp.get("ResultsByTime", []):
        amt = float(day["Total"]["UnblendedCost"]["Amount"])
        series.append((day["TimePeriod"]["Start"], amt))

    vals = [v for _, v in series]
    anomalies = []
    for i, (ts, v) in enumerate(series):
        if i < window:
            continue
        mean = sum(vals[i-window:i]) / window
        var = sum((x - mean) ** 2 for x in vals[i-window:i]) / window
        std = var ** 0.5
        score = (v - mean) / std if std > 0 else 0.0
        if score >= z:
            anomalies.append({"date": ts, "amount": v, "z": round(score, 2)})

    return {"lookbackDays": lookback_days, "z": z, "window": window, "anomalies": anomalies}