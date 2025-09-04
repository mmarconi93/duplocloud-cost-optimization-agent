import os
import shutil

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Use uvx by default if it's on PATH (pip install uv). Disable with MCP_USE_UVX=0.
USE_UVX = os.getenv("MCP_USE_UVX", "1") == "1" and shutil.which("uvx")

def _uvx(cmd: str) -> list[str]:
    # Runs the published console script from the PyPI package
    # e.g. "awslabs.cost-explorer-mcp-server"
    return ["uvx", cmd, "--stdio", "--region", AWS_REGION]

def _pythonm(module: str) -> list[str]:
    # Fallback if we preinstalled modules into the image
    return ["python", "-m", module, "--stdio", "--region", AWS_REGION]

if USE_UVX:
    PRICING_CMD = _uvx("awslabs.aws-pricing-mcp-server")
    BCM_CMD     = _uvx("awslabs.billing-cost-management-mcp-server")
    CE_CMD      = _uvx("awslabs.cost-explorer-mcp-server")
else:
    # If not using uvx, we must have these modules installed in the image.
    # we can override each via env if the module names differ.
    PRICING_CMD = _pythonm(os.getenv("MCP_PRICING_MODULE", "awslabs.pricing_mcp_server"))
    BCM_CMD     = _pythonm(os.getenv("MCP_BCM_MODULE",     "awslabs.billing_cost_management_mcp_server"))
    CE_CMD      = _pythonm(os.getenv("MCP_CE_MODULE",      "awslabs.cost_explorer_mcp_server"))

SERVERS = {
    "pricing": {"cmd": PRICING_CMD, "env": {}},
    "bcm":     {"cmd": BCM_CMD,     "env": {}},
    "ce":      {"cmd": CE_CMD,      "env": {}},
}