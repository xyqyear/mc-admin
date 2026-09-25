import asyncio

import pytest

from app.operations.finalization import finalize


async def test_owned_cleanup_failure_propagates_without_parent_cancellation():
    async def cleanup():
        raise OSError("synthetic cleanup failure")

    with pytest.raises(OSError, match="synthetic cleanup failure"):
        await finalize(cleanup())


async def test_owned_child_cancellation_propagates_without_retrying():
    async def cleanup():
        raise asyncio.CancelledError("synthetic child cancellation")

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(finalize(cleanup()), 2)
