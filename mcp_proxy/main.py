from fastapi import FastAPI, Body
from .servers import launch
from .sse_bridge import stdio_to_sse

app = FastAPI(title="MCP Proxy (STDIO <-> SSE)")

# Keep one long-lived process per server (simple cache)
procs = {"pricing": None, "bcm": None, "ce": None}

def get_proc(name: str):
    if procs[name] is None or procs[name].poll() is not None:
        procs[name] = launch(name)
    return procs[name]

@app.get("/health")
def health():
    return {"status":"ok"}

@app.post("/mcp/{server}/invoke")
async def invoke(server: str, payload: dict = Body(...)):
    if server not in procs:
        return {"error": f"unknown server '{server}'"}
    proc = get_proc(server)
    # ❌ return await stdio_to_sse(proc, payload)
    # ✅
    return stdio_to_sse(proc, payload)