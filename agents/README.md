# Agents

This directory contains the **core AWS Cost Optimization Agent**.

## Purpose

- Receives user messages via HelpDesk
- Routes them to MCP Proxy or custom tools
- Returns structured cost optimization insights

## Key Files

- `aws_cost_optimization_agent.py` → Main agent implementation
- `__init__.py` → Package initializer

## Example Queries

- `"mcp ce ping"` → Sanity check
- `"cost summary last 7 days"` → Cost Explorer summary
- `"idle assets"` → Run custom idle asset tool
- `"rightsizing recommendations"` → Run Compute Optimizer tool