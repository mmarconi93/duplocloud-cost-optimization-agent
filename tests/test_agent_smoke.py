from agents.aws_cost_optimization_agent import CostOptimizationAgent

def test_agent_echo_paths(monkeypatch):
    # Patch the names AS IMPORTED BY the agent module
    monkeypatch.setattr(
        "agents.aws_cost_optimization_agent.get_cost_summary",
        lambda **kw: {"narrative": "stub summary", "total": 0.0, "top": []},
    )
    monkeypatch.setattr(
        "agents.aws_cost_optimization_agent.get_ec2_rightsizing",
        lambda: {"count": 2, "items": [{"instanceArn": "arn:1"}, {"instanceArn": "arn:2"}]},
    )
    monkeypatch.setattr(
        "agents.aws_cost_optimization_agent.find_idle_assets",
        lambda **kw: {"unattachedVolumes": [], "unassociatedEIPs": [], "lowUtilizationInstances": []},
    )
    monkeypatch.setattr(
        "agents.aws_cost_optimization_agent.detect_anomalies",
        lambda **kw: {"anomalies": []},
    )

    agent = CostOptimizationAgent()

    # Cost summary
    msg = agent.invoke({"messages": [{"role": "user", "content": "cost summary"}]})
    assert "stub summary" in msg.content

    # Rightsizing
    msg = agent.invoke({"messages": [{"role": "user", "content": "rightsizing recommendations"}]})
    assert "2 EC2" in msg.content or "2" in msg.content

    # Idle assets
    msg = agent.invoke({"messages": [{"role": "user", "content": "idle assets"}]})
    assert "Idle/orphaned assets" in msg.content

    # Anomaly detection
    msg = agent.invoke({"messages": [{"role": "user", "content": "anomaly detection"}]})
    assert "Anomaly" in msg.content or "anomal" in msg.content