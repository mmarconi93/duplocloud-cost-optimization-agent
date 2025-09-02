# ---------- Base Python (final runtime) ----------
FROM python:3.11-slim AS pybase
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates jq \
      libfreetype6 libpng16-16 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- Node builder for AWS MCP (build stage) ----------
FROM node:20-slim AS mcpbuilder
WORKDIR /opt/aws-mcp
ARG MCP_COMMIT=main
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git clone https://github.com/awslabs/mcp.git . \
    && git checkout "$MCP_COMMIT" \
    && npm ci \
    && npm run build

# ---------- Final image (Python app + MCP dist + Node runtime only) ----------
FROM pybase AS app

# Small Node runtime so the proxy can execute MCP servers.
RUN apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY schemas/    ./schemas/
COPY agents/     ./agents/
COPY services/   ./services/
COPY tools/      ./tools/
COPY routers/    ./routers/
COPY mcp_proxy/  ./mcp_proxy/
COPY *.py        ./

# AWS MCP (built JS) from build stage
COPY --from=mcpbuilder /opt/aws-mcp/dist/ /opt/aws-mcp/dist/

# Non-root
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app /opt/aws-mcp
USER appuser

# Headless matplotlib
ENV MPLBACKEND=Agg

# Clarity: agent on 8000, proxy on 8080
EXPOSE 8000 8080

ENV LOG_LEVEL=INFO \
    AWS_REGION=us-east-1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]