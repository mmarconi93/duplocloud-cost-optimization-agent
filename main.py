"""
Run with:   python main.py
Or:         uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import logging

# dotenv optional so the app still runs if not included
try:
    import dotenv  # type: ignore
    dotenv.load_dotenv(override=True)
except Exception:
    pass

from fastapi import FastAPI
from agent_server import create_chat_app
from agents.aws_cost_optimization_agent import CostOptimizationAgent
from routers.aws_info import router as aws_info_router
from routers.cost_chart import router as cost_chart_router

logger = logging.getLogger("main")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# Initialize the agent + FastAPI app
agent = CostOptimizationAgent()
app: FastAPI = create_chat_app(agent)

# Health (for readiness/liveness checks)
@app.get("/health")
def health():
    return {"status": "ok"}

# Routers
app.include_router(aws_info_router)
app.include_router(cost_chart_router)

# Helpful startup log
USE_MCP = os.getenv("AGENT_USE_MCP", "0") == "1"
MCP_BASE = os.getenv("MCP_BASE", "http://127.0.0.1:8080")
if USE_MCP:
    logger.info("AGENT_USE_MCP=1; MCP base: %s", MCP_BASE)
else:
    logger.info("AGENT_USE_MCP=0; using local boto3 tools only")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, log_level="info")