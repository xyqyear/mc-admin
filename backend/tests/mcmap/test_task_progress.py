from app.mcmap import initialization
from app.mcmap.types import InitEvent


async def test_stage_snapshots_are_progress_until_initialization_finishes(monkeypatch):
    async def events(*args, **kwargs):
        yield InitEvent(stage="client", phase="done", percent=100)
        yield InitEvent(stage="palette", phase="pack_loaded", percent=20)
        yield InitEvent(stage="palette", phase="done", percent=100)
        yield InitEvent(stage="complete")

    monkeypatch.setattr(initialization, "initialize_events", events)
    updates = [update async for update in initialization.initialize_task("alpha", False, 1)]
    assert all(update.result is None for update in updates[:-1])
    assert updates[1].progress == 60
    details = updates[1].progress_details
    assert details is not None and details["kind"] == "map"
    assert details["stages"]["client"]["phase"] == "done"
    assert details["stages"]["palette"]["percent"] == 20
    assert updates[-1].result is not None
    assert updates[-1].result["stages"]["palette"]["phase"] == "done"
