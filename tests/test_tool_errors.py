from agents.aws_cost_optimization_agent import CostOptimizationAgent

def test_tool_error_path(monkeypatch):
    def boom(**kw): raise Exception("CE throttled")
    monkeypatch.setattr("agents.aws_cost_optimization_agent.get_cost_summary", boom)
    msg = CostOptimizationAgent().invoke({"messages":[{"role":"user","content":"cost summary"}]})
    assert "CE throttled" in msg.content or "error" in msg.content.lower()