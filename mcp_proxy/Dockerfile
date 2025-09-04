# ---------- MCP Proxy (uses uvx to run AWS MCP servers) ----------
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Basic OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install uv (installs into /root/.local/bin)
RUN curl -Ls https://astral.sh/uv/install.sh | sh

# Copy uv and uvx to a system path with world-exec perms
RUN install -m 0755 /root/.local/bin/uv  /usr/local/bin/uv  && \
    install -m 0755 /root/.local/bin/uvx /usr/local/bin/uvx && \
    uv --version && uvx --version

WORKDIR /app

# Install Python deps for the proxy itself
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the proxy code (assuming this Dockerfile lives in mcp_proxy/)
COPY . /app/mcp_proxy

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser \
 && chown -R appuser:appuser /app
USER appuser

# Default region (can be overridden at runtime)
ENV AWS_REGION=us-east-1
# Force servers.py to use uvx path (belt & suspenders)
ENV MCP_USE_UVX=1

EXPOSE 8080

# Start the proxy (FastAPI)
CMD ["uvicorn", "mcp_proxy.main:app", "--host", "0.0.0.0", "--port", "8080"]