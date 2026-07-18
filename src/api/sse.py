"""Server-Sent Events helpers.

`stream()` from the agent graph is a *blocking sync generator*. Starlette's
`StreamingResponse` iterates a sync generator in a threadpool automatically, so the
event loop is never blocked — the routers can hand it a plain sync generator of the
strings produced here.
"""

from __future__ import annotations

import json
from typing import Any

# Headers that keep SSE flowing through dev proxies / reverse proxies: disable caching
# and nginx-style response buffering so each event reaches the client immediately.
SSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def sse_event(event: str, data: dict[str, Any]) -> str:
    """Format one named SSE frame: `event: <e>\\ndata: <json>\\n\\n`."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
