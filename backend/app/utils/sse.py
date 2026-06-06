from __future__ import annotations

import json
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def sse_encode(payload: Any) -> bytes:
    payload = jsonable_encoder(payload, exclude_none=True)
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()


def sse_response(events: AsyncIterable[Any]) -> StreamingResponse:
    async def encoded_events() -> AsyncIterator[bytes]:
        async for event in events:
            if isinstance(event, bytes):
                yield event
            else:
                yield sse_encode(event)

    return StreamingResponse(
        encoded_events(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
