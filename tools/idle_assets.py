# tools/idle_assets.py
import os
import boto3
import datetime

def find_idle_assets(lookback_days=14, cpu_threshold=5.0):
    ec2 = boto3.client("ec2", region_name=os.getenv("AWS_REGION", "us-east-1"))
    cw  = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "us-east-1"))
    now = datetime.datetime.utcnow()
    start = now - datetime.timedelta(days=lookback_days)

    # Unattached EBS (paginate)
    unattached = []
    token = None
    while True:
        kwargs = {"Filters": [{"Name": "status", "Values": ["available"]}]}
        if token:
            kwargs["NextToken"] = token
        resp = ec2.describe_volumes(**kwargs)
        for v in resp.get("Volumes", []):
            unattached.append({"volumeId": v.get("VolumeId"), "sizeGiB": v.get("Size")})
        token = resp.get("NextToken")
        if not token:
            break

    # Unassociated EIPs (may not paginate)
    eips = []
    addr_resp = ec2.describe_addresses()
    for a in addr_resp.get("Addresses", []):
        if "AssociationId" not in a:
            eips.append(a.get("PublicIp"))

    # Low-CPU EC2 (paginate)
    low = []
    token = None
    while True:
        kwargs = {}
        if token:
            kwargs["NextToken"] = token
        resp = ec2.describe_instances(**kwargs)
        for res in resp.get("Reservations", []):
            for i in res.get("Instances", []):
                if (i.get("State", {}).get("Name") or "").lower() != "running":
                    continue
                iid = i.get("InstanceId")
                if not iid:
                    continue
                m = cw.get_metric_statistics(
                    Namespace="AWS/EC2",
                    MetricName="CPUUtilization",
                    Dimensions=[{"Name": "InstanceId", "Value": iid}],
                    StartTime=start,
                    EndTime=now,
                    Period=3600,  # 1 hour
                    Statistics=["Average"],
                )
                pts = m.get("Datapoints", [])
                if pts:
                    avg = sum(p.get("Average", 0.0) for p in pts) / max(1, len(pts))
                    if avg < cpu_threshold:
                        low.append({"instanceId": iid, "avgCPU": round(avg, 2), "type": i.get("InstanceType")})
        token = resp.get("NextToken")
        if not token:
            break

    return {
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