# ---------- Cost Optimization Agent ----------
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg

# OS deps for plotting and curl (no git needed here)
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates libfreetype6 libpng16-16 fonts-dejavu-core \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (agent only)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY schemas/    ./schemas/
COPY agents/     ./agents/
COPY services/   ./services/
COPY tools/      ./tools/
COPY routers/    ./routers/
COPY *.py        ./

# Non-root
RUN adduser --disabled-password --gecos '' appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
ENV LOG_LEVEL=INFO AWS_REGION=us-east-1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]