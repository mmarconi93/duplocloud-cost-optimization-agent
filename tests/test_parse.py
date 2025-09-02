from agents.aws_cost_optimization_agent import CostOptimizationAgent

def invoke(text):
    return CostOptimizationAgent().invoke({"messages":[{"role":"user","content":text}]})

def test_parse_lookback_default(monkeypatch):
    monkeypatch.setattr("agents.aws_cost_optimization_agent.get_cost_summary",
                        lambda **kw: {"narrative":"ok"})
    msg = invoke("cost summary")
    assert "ok" in msg.content

def test_parse_lookback_custom(monkeypatch):
    calls = {}
    def fake(**kw): 
        calls.update(kw); return {"narrative":"ok"}
    monkeypatch.setattr("agents.aws_cost_optimization_agent.get_cost_summary", fake)
    invoke("cost summary last 7 days")
    assert calls["lookback_days"] == 7

def test_parse_tag(monkeypatch):
    captured = {}
    def fake(**kw): captured.update(kw); return {"narrative":"ok"}
    monkeypatch.setattr("agents.aws_cost_optimization_agent.get_cost_summary", fake)
    invoke("cost summary tag:Environment")
    assert captured["group_by"] == "TAG" and captured["tag_key"] == "Environment"