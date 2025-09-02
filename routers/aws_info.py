from fastapi import APIRouter
import boto3

router = APIRouter(tags=["diagnostics"])

@router.get("/aws/whoami")
def whoami():
    sts = boto3.client("sts")
    return sts.get_caller_identity()