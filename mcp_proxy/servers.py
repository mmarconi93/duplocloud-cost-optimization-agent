import os
import subprocess
import shlex

# Commands for the 3 MCP servers; passing creds via IRSA (in-cluster)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

SERVERS = {
    "pricing": {
        "cmd": shlex.split(os.getenv("MCP_PRICING_CMD", "aws-pricing-mcp --region "+AWS_REGION)),
        "env": {}
    },
    "bcm": {
        "cmd": shlex.split(os.getenv("MCP_BCM_CMD", "aws-billing-mcp --region "+AWS_REGION)),
        "env": {}
    },
    "ce": {
        "cmd": shlex.split(os.getenv("MCP_CE_CMD", "aws-cost-explorer-mcp --region "+AWS_REGION)),
        "env": {}
    },
}

def launch(name: str) -> subprocess.Popen:
    spec = SERVERS[name]
    return subprocess.Popen(
        spec["cmd"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, **spec.get("env", {})},
        bufsize=1,
        text=True,
        encoding="utf-8",
        errors="replace",
        close_fds=True,
    )