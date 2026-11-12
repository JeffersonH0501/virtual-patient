"""Bind a per-request trace id so performance events correlate across tiers.

The frontend sends an ``X-Trace-Id`` header (see the UI ``apiFetch`` wrapper);
this middleware binds it for the request so ``performance_event`` lines emitted
while handling that request carry the same ``trace_id``. When the header is
absent (non-browser caller or disabled UI), a short server id is generated so
every request is still self-correlatable. The id is echoed back in the response
header for client-side logging.

Only an opaque short token is accepted; it never carries personal data.
"""

from __future__ import annotations

from uuid import uuid4

from starlette.types import ASGIApp, Receive, Scope, Send

from app.utils.perf import set_trace_id

_HEADER = b"x-trace-id"
_MAX_LEN = 64


class TraceIdMiddleware:
    """Pure-ASGI middleware (no Starlette BaseHTTPMiddleware task-copy cost)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or {}).get(_HEADER)
        trace_id = incoming.decode("ascii", "ignore")[:_MAX_LEN].strip() if incoming else ""
        if not trace_id:
            trace_id = uuid4().hex[:16]
        set_trace_id(trace_id)

        async def send_with_trace(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((_HEADER, trace_id.encode("ascii", "ignore")))
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            set_trace_id(None)
