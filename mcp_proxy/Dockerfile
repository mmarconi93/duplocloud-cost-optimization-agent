# ---------- MCP Proxy + AWS MCP Servers ----------
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates unzip \
  && rm -rf /var/lib/apt/lists/*

# Install uv (used by the AWS MCP repos)
RUN curl -Ls https://astral.sh/uv/install.sh | sh \
 && ln -s /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# Proxy deps (relative to build context: ./mcp_proxy)
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Put the proxy code under /app/mcp_proxy so import path stays the same
COPY . ./mcp_proxy

# Download public AWS MCP repo (no git, no auth)
# NOTE: correct repo is awslabs/mcp (not awslabs/aws-mcp)
RUN curl -L https://codeload.github.com/awslabs/mcp/zip/refs/heads/main -o /tmp/mcp.zip \
 && unzip /tmp/mcp.zip -d /app \
 && mv /app/mcp-main /app/mcp \
 && rm /tmp/mcp.zip

# Create venvs for the 3 servers
WORKDIR /app/mcp/src/aws-pricing-mcp-server
RUN uv sync

WORKDIR /app/mcp/src/billing-cost-management-mcp-server
RUN uv sync

WORKDIR /app/mcp/src/cost-explorer-mcp-server
RUN uv sync

# Back to proxy root
WORKDIR /app

# Non-root
RUN adduser --disabled-password --gecos '' appuser \
 && chown -R appuser:appuser /app
USER appuser

# Default region (override in runtime)
ENV AWS_REGION=us-east-1

# Use the local venv-installed server binaries
ENV MCP_PRICING_CMD="bash -lc 'cd /app/mcp/src/aws-pricing-mcp-server && .venv/bin/awslabs.aws-pricing-mcp-server --stdio --region $AWS_REGION'"
ENV MCP_BCM_CMD="bash -lc 'cd /app/mcp/src/billing-cost-management-mcp-server && .venv/bin/awslabs.billing-cost-management-mcp-server --stdio --region $AWS_REGION'"
ENV MCP_CE_CMD="bash -lc 'cd /app/mcp/src/cost-explorer-mcp-server && .venv/bin/awslabs.cost-explorer-mcp-server --stdio --region $AWS_REGION'"

EXPOSE 8080

# Keep module path the same: mcp_proxy.main:app now lives at /app/mcp_proxy/main.py
CMD ["uvicorn", "mcp_proxy.main:app", "--host", "0.0.0.0", "--port", "8080"]