from __future__ import annotations

import os
import datetime as dt
from typing import Dict, Any, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def _region() -> str:
    return os.getenv("AWS_REGION", "us-east-1")


def _utc_now() -> dt.datetime:
    # CloudWatch expects UTC timestamps. Making them timezone-aware.
    return dt.datetime.now(dt.timezone.utc)


def _paginate(method, result_key: str, **kwargs):
    """Generic paginator helper for boto3 'NextToken' style APIs."""
    token = None
    while True:
        call_kwargs = dict(**kwargs)
        if token:
            call_kwargs["NextToken"] = token
        resp = method(**call_kwargs)
        for item in resp.get(result_key, []) or []:
            yield item
        token = resp.get("NextToken")
        if not token:
            break


def find_idle_assets(lookback_days: int = 14, cpu_threshold: float = 5.0) -> Dict[str, Any]:
    """
    Find:
      - unattached EBS volumes
      - unassociated Elastic IPs
      - EC2 instances with average CPU utilization below `cpu_threshold` over the last `lookback_days`

    Returns:
      {
        "unattachedVolumes": [{"volumeId": "...", "sizeGiB": 8}, ...],
        "unassociatedEIPs": ["x.x.x.x", ...],
        "lowUtilizationInstances": [{"instanceId": "...", "avgCPU": 2.1, "type": "t3.micro"}, ...],
        "lookbackDays": int,
        "cpuThreshold": float,
        "actions": [...]
      }
    """
    region = _region()
    ec2 = boto3.client("ec2", region_name=region)
    cw = boto3.client("cloudwatch", region_name=region)

    now = _utc_now()
    # CloudWatch: choose end aligned to now, start lookback_days ago
    start = now - dt.timedelta(days=lookback_days)

    unattached: List[Dict[str, Any]] = []
    eips: List[str] = []
    low: List[Dict[str, Any]] = []

    # -------- Unattached EBS volumes --------
    try:
        for v in _paginate(
            ec2.describe_volumes,
            "Volumes",
            Filters=[{"Name": "status", "Values": ["available"]}],
        ):
            unattached.append(
                {
                    "volumeId": v.get("VolumeId"),
                    "sizeGiB": v.get("Size"),
                    "az": (v.get("AvailabilityZone") or ""),
                    "createTime": (v.get("CreateTime").isoformat() if v.get("CreateTime") else None),
                }
            )
    except (ClientError, BotoCoreError) as e:
        # Non-fatal: just note that part of the scan failed
        unattached = []
        eips_note = f"Skipped unattached volumes due to error: {e}"
    else:
        eips_note = None

    # -------- Unassociated Elastic IPs (paginate) --------
    try:
        # Newer API supports MaxResults/NextToken in some regions; handle both
        token = None
        while True:
            kwargs = {}
            if token:
                kwargs["NextToken"] = token
            resp = ec2.describe_addresses(**kwargs)
            for a in resp.get("Addresses", []) or []:
                if "AssociationId" not in a:
                    ip = a.get("PublicIp")
                    if ip:
                        eips.append(ip)
            token = resp.get("NextToken")
            if not token:
                break
    except (ClientError, BotoCoreError) as e:
        eips = []
        eips_note2 = f"Skipped EIP scan due to error: {e}"
    else:
        eips_note2 = None

    # -------- Low-CPU EC2 instances --------
    # Collect running instance IDs first (paginated)
    running: List[Dict[str, Any]] = []
    try:
        for res in _paginate(ec2.describe_instances, "Reservations"):
            for inst in res.get("Instances", []) or []:
                if (inst.get("State", {}).get("Name") or "").lower() != "running":
                    continue
                iid = inst.get("InstanceId")
                if iid:
                    running.append({"id": iid, "type": inst.get("InstanceType")})
    except (ClientError, BotoCoreError) as e:
        running = []
        low_note = f"Skipped instance scan due to error: {e}"
    else:
        low_note = None

    # Batch CPU metrics with GetMetricData to avoid N calls (limit 500 metrics per req)
    if running:
        # 1-hour aggregation is fine for multi-day lookbacks
        period = 3600
        # CloudWatch GetMetricData supports up to 500 MetricDataQueries
        batch_size = 400  # leave headroom
        try:
            for i in range(0, len(running), batch_size):
                batch = running[i : i + batch_size]
                queries = []
                for idx, inst in enumerate(batch):
                    qid = f"m{idx}"
                    queries.append(
                        {
                            "Id": qid,
                            "MetricStat": {
                                "Metric": {
                                    "Namespace": "AWS/EC2",
                                    "MetricName": "CPUUtilization",
                                    "Dimensions": [{"Name": "InstanceId", "Value": inst["id"]}],
                                },
                                "Period": period,
                                "Stat": "Average",
                            },
                            "ReturnData": True,
                        }
                    )

                resp = cw.get_metric_data(
                    MetricDataQueries=queries,
                    StartTime=start,
                    EndTime=now,
                    ScanBy="TimestampAscending",
                )

                # Map id->avg
                id_to_avg: Dict[str, float] = {}
                for r in resp.get("MetricDataResults", []) or []:
                    # r["Id"] is m{idx} in our batch
                    idx = int(r["Id"][1:])
                    inst = batch[idx]
                    vals = r.get("Values", []) or []
                    if vals:
                        avg = sum(vals) / len(vals)
                        id_to_avg[inst["id"]] = avg

                for inst in batch:
                    avg = id_to_avg.get(inst["id"], None)
                    if avg is not None and avg < cpu_threshold:
                        low.append(
                            {
                                "instanceId": inst["id"],
                                "avgCPU": round(float(avg), 2),
                                "type": inst.get("type"),
                            }
                        )
        except (ClientError, BotoCoreError) as e:
            # If metrics fail, still return the other sections
            low = []
            low_note = f"Skipped CPU analysis due to error: {e}"

    result: Dict[str, Any] = {
        "unattachedVolumes": unattached,
        "unassociatedEIPs": eips,
        "lowUtilizationInstances": low,
        "lookbackDays": lookback_days,
        "cpuThreshold": cpu_threshold,
        "actions": [
            "Snapshot then delete unattached volumes.",
            "Release unassociated Elastic IPs.",
            f"Downsize or schedule stop for instances with avg CPU < {cpu_threshold}%.",
        ],
    }

    # Include non-fatal notes if any sections were skipped
    notes = [n for n in [eips_note, eips_note2, low_note] if n]
    if notes:
        result["notes"] = notes

    return result