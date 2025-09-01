FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc curl jq util-linux gawk && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only necessary files (exclude .env, .git, etc.)
COPY schemas/ ./schemas/
COPY agents/ ./agents/
COPY services/ ./services/
COPY *.py ./

# Expose the port the app runs on
EXPOSE 8000

# Set environment variables with defaults that can be overridden
ENV LOG_LEVEL=INFO \
    AWS_REGION=us-east-1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]