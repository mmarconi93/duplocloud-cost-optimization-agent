from __future__ import annotations
import os, json, requests
from typing import Any, Dict, List, Optional

DEFAULT_BASE = os.getenv("MCP_BASE", "http://127.0.0.1:8080")

class MCPClient:
    def __init__(self, base_url: Optional[str] = None, session: Optional[requests.Session] = None) -> None:
        self.base_url = (base_url or DEFAULT_BASE).rstrip("/")
        self.s = session or requests.Session()

    def health(self) -> Dict[str, Any]:
        r = self.s.get(f"{self.base_url}/health", timeout=5)
        r.raise_for_status()
        return r.json()

    def invoke(self, server: str, payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
        url = f"{self.base_url}/mcp/{server}/invoke"
        r = self.s.post(url, json=payload, stream=True, timeout=timeout)
        r.raise_for_status()
        frames, raw_lines = [], []
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            raw_lines.append(line)
            if line.startswith("data:"):
                data = line[5:].strip()
                try:
                    frames.append(json.loads(data))
                except Exception:
                    frames.append({"_raw": data})
                break  # only expect one line from proxy
        return {"frames": frames, "last": (frames[-1] if frames else None), "raw_lines": raw_lines}

# module-level singleton-style helpers
_client = MCPClient()

def health() -> Dict[str, Any]:
    return _client.health()

def invoke(server: str, payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    return _client.invoke(server, payload, timeout=timeout)