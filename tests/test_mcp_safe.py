from agents.aws_cost_optimization_agent import CostOptimizationAgent

def test_mcp_ce_safe(monkeypatch):
    # Simulate proxy/MCP being unavailable
    def boom(*a, **k): raise Exception("proxy down")
    monkeypatch.setattr("agents.aws_cost_optimization_agent.mcp_invoke", boom)

    agent = CostOptimizationAgent()
    msg = agent.invoke({"messages":[{"role":"user","content":"mcp ce ping"}]})
    assert "Sorry, mcp ce ping failed: proxy down" in msg.content