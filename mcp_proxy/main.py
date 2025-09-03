from fastapi import FastAPI, Body
from .servers import SERVERS
from .sse_bridge import stdio_to_sse

app = FastAPI(title="MCP Proxy (MCP client ↔ SSE)")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/mcp/{server}/invoke")
async def invoke(server: str, payload: dict = Body(...)):
    """
    Bridges HTTP -> (spawn MCP server over stdio) -> SSE back to the client.
    Use with an SSE-capable client (or pipe through `ssejq` like you did).
    """
    if server not in SERVERS:
        return {"error": f"unknown server '{server}'"}
    cmd = SERVERS[server]["cmd"]
    return await stdio_to_sse(cmd, payload)