from __future__ import annotations

import json
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from anyio import CancelScope
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from starlette.types import Send

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class _SSEStreamingResponse(StreamingResponse):
    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                with CancelScope(shield=True):
                    await close()


def sse_encode(payload: Any) -> bytes:
    payload = jsonable_encoder(payload, exclude_none=True)
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()


def sse_response(events: AsyncIterable[Any]) -> StreamingResponse:
    async def encoded_events() -> AsyncIterator[bytes]:
        try:
            async for event in events:
                if isinstance(event, bytes):
                    yield event
                else:
                    yield sse_encode(event)
        finally:
            close = getattr(events, "aclose", None)
            if close is not None:
                with CancelScope(shield=True):
                    await close()

    return _SSEStreamingResponse(
        encoded_events(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
