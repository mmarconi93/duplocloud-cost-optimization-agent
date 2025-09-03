# Tools

This directory contains **custom agentic tools** that extend the AWS Cost Optimization Agent.  
Each tool provides additional insights beyond the AWS MCP servers.

## Available Tools

- **`idle_assets.py`**
  - Detects unused EC2 instances, EBS volumes, and Elastic IPs
  - Helps identify opportunities for cost savings by decommissioning idle resources

- **`cost_anomaly.py`**
  - Identifies anomalous AWS spending patterns
  - Useful for early detection of unexpected spikes

- **`cost_explorer.py`**
  - Queries AWS Cost Explorer via MCP proxy
  - Provides summaries, breakdowns, and forecasts

- **`compute_optimizer.py`**
  - Surfaces Compute Optimizer recommendations (rightsizing EC2)
  - Requires appropriate IAM permissions

## Adding a New Tool

1. Create a new `.py` file in this directory.
2. Implement your logic (e.g., AWS API calls or custom analysis).
3. Export a function that can be called by the **agent**.
4. Register the tool inside the agent routing (`agents/aws_cost_optimization_agent.py`).

Example:
```python
def my_new_tool(params: dict) -> dict:
    return {"message": "Hello from my tool"}
```