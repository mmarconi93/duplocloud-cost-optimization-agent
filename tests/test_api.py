from fastapi.testclient import TestClient
from main import app

def test_health():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"

def test_send_message_smoke(monkeypatch):
    from agents import aws_cost_optimization_agent as mod
    monkeypatch.setattr(mod, "get_cost_summary", lambda **kw: {"narrative":"ok"})
    c = TestClient(app)
    r = c.post("/api/sendMessage", json={"messages":[{"role":"user","content":"cost summary"}]})
    assert r.status_code == 200
    assert "ok" in r.json()["content"]