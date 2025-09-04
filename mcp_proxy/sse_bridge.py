import json
import shlex
from typing import Any, Dict, List, Optional, Sequence, Union

from fastapi.responses import StreamingResponse

# MCP client (v1.11+)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _normalize_cmd(cmd: Union[str, Sequence[str]]):
    """
    Accept either a single command string or a pre-split list/tuple.
    Return (command: str, args: List[str]) suitable for StdioServerParameters.
    """
    if isinstance(cmd, (list, tuple)):
        if not cmd:
            raise ValueError("Empty command list provided to stdio_to_sse.")
        command, *args = cmd
    else:
        parts = shlex.split(cmd)
        if not parts:
            raise ValueError("Empty command string provided to stdio_to_sse.")
        command, *args = parts
    return command, args


async def stdio_to_sse(
    cmd: Union[str, List[str]],
    payload: Dict[str, Any],
    *,
    env: Optional[Dict[str, str]] = None,
):
    """
    Spawn an MCP server (stdio transport), perform handshake, optionally list tools,
    or call a specific tool with `params`, and stream a single SSE message back.
    """
    async def _gen():
        command, args = _normalize_cmd(cmd)
        server = StdioServerParameters(command=command, args=args, env=env or {})

        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                # Handshake
                await session.initialize()

                # ---- Discovery: list tools ----
                if payload.get("list_tools"):
                    tools = await session.list_tools()
                    out = tools.model_dump(mode="json") if hasattr(tools, "model_dump") else tools
                    yield "data: " + json.dumps({"ok": True, "tools": out}) + "\n\n"
                    return

                # ---- Health probe ----
                if payload.get("ping"):
                    # If we got here, the server started & handshake succeeded.
                    yield "data: " + json.dumps({"ok": True}) + "\n\n"
                    return

                # ---- Tool call ----
                tool_name: Optional[str] = payload.get("tool")
                params: Dict[str, Any] = payload.get("params", {}) or {}

                if not tool_name:
                    yield "data: " + json.dumps({"error": "no tool specified"}) + "\n\n"
                    return

                try:
                    result = await session.call_tool(tool_name, arguments=params)
                    out = {
                        "ok": True,
                        "tool": tool_name,
                        "result": (
                            result.model_dump(mode="json")
                            if hasattr(result, "model_dump")
                            else result
                        ),
                    }
                    yield "data: " + json.dumps(out) + "\n\n"
                except Exception as e:
                    err = {"ok": False, "tool": tool_name, "error": str(e)}
                    yield "data: " + json.dumps(err) + "\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")