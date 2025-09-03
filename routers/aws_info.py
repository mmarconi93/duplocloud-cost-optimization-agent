from fastapi import APIRouter, HTTPException
import boto3
from botocore.exceptions import BotoCoreError, ClientError

router = APIRouter(tags=["diagnostics"])


@router.get("/aws/whoami")
def whoami():
    """
    Quick identity check for the configured AWS credentials.
    Returns account, ARN, userId, and the boto3 session region.
    """
    try:
        sts = boto3.client("sts")
        ident = sts.get_caller_identity()
        session = boto3.session.Session()
        return {
            "account": ident.get("Account"),
            "arn": ident.get("Arn"),
            "userId": ident.get("UserId"),
            "region": session.region_name or "us-east-1",
        }
    except (BotoCoreError, ClientError) as e:
        # Surface a clean 502 with the AWS error string (no secrets are exposed)
        raise HTTPException(status_code=502, detail=f"AWS error: {e}")