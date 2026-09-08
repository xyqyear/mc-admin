import asyncio

import anyio
import pytest
from anyio.lowlevel import checkpoint

from app.utils.sse import sse_response


@pytest.mark.parametrize("cancel_scope", [False, True])
async def test_disconnect_during_send_closes_source_before_return(cancel_scope):
    closed = asyncio.Event()

    async def events():
        try:
            yield {"event_type": "start"}
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            closed.set()

    response = sse_response(events())
    with anyio.CancelScope() as scope:

        async def send(message):
            if message["type"] == "http.response.body":
                if cancel_scope:
                    scope.cancel()
                    await checkpoint()
                raise OSError("disconnected")

        if cancel_scope:
            await response.stream_response(send)
        else:
            with pytest.raises(OSError, match="disconnected"):
                await response.stream_response(send)
    assert closed.is_set()
