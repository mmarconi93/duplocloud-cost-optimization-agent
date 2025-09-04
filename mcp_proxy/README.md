
# MCP Proxy

The MCP Proxy is a **FastMCP-based proxy** that bridges AWS MCP servers into the agent.

## Purpose

- Converts **STDIO ↔ SSE** communication so that FastAPI can consume MCP servers as HTTP endpoints.
- Allows the cost optimization agent to query:
  - AWS Pricing MCP Server
  - AWS Billing & Cost Management MCP Server
  - AWS Cost Explorer MCP Server

## Key Files

- `main.py` → FastAPI entrypoint for proxy
- `servers.py` → MCP server spawn logic
- `sse_bridge.py` → Handles conversion from STDIO to SSE transport
- `requirements.txt` → Proxy dependencies
- `Dockerfile` → Container image definition

## Usage

Run the proxy locally:
```bash
uvicorn mcp_proxy.main:app --host 0.0.0.0 --port 8080
```
Health check:
```bash
curl http://localhost:8080/health
```

## Kubernetes
In cluster, the proxy runs as a Deployment + Service.
It should be associated with an IAM role (IRSA) that grants access to:
- Pricing API
- Cost Explorer API
- Billing & Cost Management

## Use in AI Studio -> HelpDesk
To ping and test MCP server connectivitiy between the agent, do the following from inside the `HelpDesk`:
```bash
mcp pricing ping
```
```bash
mcp bcm ping
```
```bash
mcp ce ping
```