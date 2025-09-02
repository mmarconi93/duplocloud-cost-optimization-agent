import os
import boto3

def get_ec2_rightsizing():
    co = boto3.client("compute-optimizer", region_name=os.getenv("AWS_REGION", "us-east-1"))
    resp = co.get_ec2_instance_recommendations()
    items = []
    for r in resp.get("instanceRecommendations", []):
        opts = r.get("recommendationOptions", [])
        top = opts[0] if opts else {}
        savings = (top.get("savingsOpportunity", {}) or {}).get("estimatedMonthlySavings", {})

        items.append({
            "instanceArn": r.get("instanceArn"),
            "instanceId": r.get("instanceId"),
            "currentType": r.get("currentInstanceType"),
            "recommendations": [o.get("instanceType") for o in opts[:3] if o.get("instanceType")],
            "estimatedMonthlySavings": savings,
            "finding": r.get("finding"),         # e.g., Overprovisioned, Underprovisioned, etc.
        })
    return {"count": len(items), "items": items}
