"""
Run with:   python main.py
Or:         uvicorn main:app --port 8000 --reload
"""

import os
import dotenv
from agent_server import create_chat_app
from agents.aws_cost_optimization_agent import CostOptimizationAgent
from routers.aws_info import router as aws_info_router
from routers.cost_chart import router as cost_chart_router

# Load .env (useful for local, but optional for cluster)
dotenv.load_dotenv(override=True)

# Initialize the agent
agent = CostOptimizationAgent()
app = create_chat_app(agent)
app.include_router(aws_info_router)
app.include_router(cost_chart_router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, log_level="info")