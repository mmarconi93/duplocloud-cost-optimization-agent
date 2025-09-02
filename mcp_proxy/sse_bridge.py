import json
import time
from typing import AsyncGenerator
from fastapi.responses import StreamingResponse

READ_TIMEOUT_SEC = 20  # don't hang forever during local tests

def stdio_to_sse(proc, payload: dict) -> StreamingResponse:
    """
    Writes one JSON line to the STDIO MCP server, flushes, then streams back
    exactly one line as text/event-stream ("data: <json>\n\n").
    """

    # ---- Write request line (CRITICAL: newline + flush) ----
    line = json.dumps(payload)
    if proc.stdin is None:
        def _err():
            yield 'data: {"error":"stdin closed"}\n\n'
        return StreamingResponse(_err(), media_type="text/event-stream")

    try:
        # proc was opened in text=True below; write str
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
    except Exception as e:
        def _err():
            yield f'data: {json.dumps({"error": f"write failed: {e}"})}\n\n'
        return StreamingResponse(_err(), media_type="text/event-stream")

    # ---- Read a single response line and stream as SSE ----
    def _stream():
        start = time.time()
        while True:
            if proc.stdout is None:
                yield 'data: {"error":"stdout closed"}\n\n'
                return

            out = proc.stdout.readline()
            if out:
                out = out.strip()
                # If not valid JSON, wrap it so the client always gets JSON
                try:
                    json.loads(out)
                    data = out
                except Exception:
                    data = json.dumps({"raw": out})
                yield f"data: {data}\n\n"
                return

            if time.time() - start > READ_TIMEOUT_SEC:
                yield 'data: {"error":"no output from MCP subprocess"}\n\n'
                return
            time.sleep(0.1)

    return StreamingResponse(_stream(), media_type="text/event-stream")
