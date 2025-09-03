import os
import shlex
import subprocess

# Default region (overridable via env)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# These defaults use the console script names exposed by each package.
# You can override any of them with MCP_*_CMD env vars (as you've done for local venv paths).
SERVERS = {
    "pricing": {
        "cmd": shlex.split(os.getenv(
            "MCP_PRICING_CMD",
            f"uvx awslabs.aws-pricing-mcp-server --stdio --region {AWS_REGION}"
        )),
        "env": {},
    },
    "bcm": {
        "cmd": shlex.split(os.getenv(
            "MCP_BCM_CMD",
            # NOTE: console script is *billing-cost-management* (no leading 'aws-')
            f"uvx awslabs.billing-cost-management-mcp-server --stdio --region {AWS_REGION}"
        )),
        "env": {},
    },
    "ce": {
        "cmd": shlex.split(os.getenv(
            "MCP_CE_CMD",
            f"uvx awslabs.cost-explorer-mcp-server --stdio --region {AWS_REGION}"
        )),
        "env": {},
    },
}

def launch(name: str) -> subprocess.Popen:
    """
    Optional helper if you ever want to manage a long-lived child yourself.
    Not used by the current SSE bridge (which spawns per-request).
    """
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