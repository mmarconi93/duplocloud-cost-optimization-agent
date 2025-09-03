import os
from typing import Dict, Any, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def get_ec2_rightsizing() -> Dict[str, Any]:
    """
    Fetch EC2 rightsizing recommendations from Compute Optimizer.
    Handles pagination and returns a compact, agent-friendly shape.

    Returns:
        {
          "count": int,
          "items": [
            {
              "instanceArn": str,
              "instanceId": str,
              "currentType": str,
              "recommendations": [str, ...],         # up to 3 types
              "estimatedMonthlySavings": {...},      # amount/currency
              "finding": str                         # Overprovisioned, Underprovisioned, ...
            },
            ...
          ]
        }
        On access/opt-in errors, returns {"count": 0, "items": [], "note": "..."}.
    """
    region = os.getenv("AWS_REGION", "us-east-1")
    co = boto3.client("compute-optimizer", region_name=region)

    items: List[Dict[str, Any]] = []
    token = None
    try:
        while True:
            kwargs = {}
            if token:
                kwargs["nextToken"] = token

            resp = co.get_ec2_instance_recommendations(**kwargs)

            for r in resp.get("instanceRecommendations", []) or []:
                opts = r.get("recommendationOptions", []) or []
                top = opts[0] if opts else {}
                savings = (top.get("savingsOpportunity") or {}).get("estimatedMonthlySavings", {}) or {}

                items.append(
                    {
                        "instanceArn": r.get("instanceArn"),
                        "instanceId": r.get("instanceId"),
                        "currentType": r.get("currentInstanceType"),
                        "recommendations": [
                            o.get("instanceType") for o in opts[:3] if o.get("instanceType")
                        ],
                        "estimatedMonthlySavings": savings,
                        "finding": r.get("finding"),
                    }
                )

            token = resp.get("nextToken")
            if not token:
                break

        return {"count": len(items), "items": items}

    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        # Common scenarios: AccessDeniedException, OptInRequiredException, ThrottlingException
        note = f"Compute Optimizer error ({code}): {e}"
        return {"count": 0, "items": [], "note": note}
    except BotoCoreError as e:
        return {"count": 0, "items": [], "note": f"Compute Optimizer error: {e}"}