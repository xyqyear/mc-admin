import asyncio
import json
from contextlib import aclosing

import pytest

from app.execution_observation import snapshot
from app.snapshots.scopes import PathsScope


@pytest.mark.binary("restic")
@pytest.mark.binary("fd")
@pytest.mark.parametrize("reject", [False, True])
async def test_committed_restoration_notifies_before_task_registration(case, monkeypatch, reject):
    target = case.data / "settings.txt"
    target.write_text("source A")
    source = await case.snapshots.create_snapshot([target])
    target.write_text("current B")
    committed, release = asyncio.Event(), asyncio.Event()
    phase = case.journal.phase

    async def held_acceptance(operation_id, name, **kwargs):
        if name == "accepted":
            committed.set()
            await release.wait()
        return await phase(operation_id, name, **kwargs)

    monkeypatch.setattr(case.journal, "phase", held_acceptance)
    async with aclosing(case.tasks.events(get_index=snapshot)) as stream:
        initial = json.loads((await anext(stream))[6:])
        assert initial["active_restorations"] == []
        submitting = asyncio.create_task(case.commands.restore(PathsScope(server_id="survival", paths=("settings.txt",)), source.id, 1))
        try:
            await asyncio.wait_for(committed.wait(), 5)
            async with asyncio.timeout(5):
                while True:
                    event = json.loads((await anext(stream))[6:])
                    if event["type"] == "restoration_index" and event["active_restorations"]:
                        break
            row = event["active_restorations"][0]
            assert row["status"] == "pending"
            assert row["targets"] == [{"server_id": "survival", "generation": 1}]
            assert row["scope"] == {"kind": "paths", "server_id": "survival", "paths": ["settings.txt"]}
            assert case.tasks.get_task(row["operation_id"]) is None
            assert target.read_text() == "current B"
            if reject:
                submitting.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await submitting
                async with asyncio.timeout(5):
                    while True:
                        event = json.loads((await anext(stream))[6:])
                        if event["type"] == "restoration_index" and not event["active_restorations"]:
                            break
                assert case.tasks.get_task(row["operation_id"]) is None
        finally:
            release.set()
            if reject:
                submitting.cancel()
                await asyncio.gather(submitting, return_exceptions=True)
            else:
                accepted = await submitting
                future = case.tasks.get_future(accepted["task_id"])
                assert future is not None
                await case.tasks.cancel(accepted["task_id"])
                await asyncio.wait_for(future, 10)
    assert await snapshot("restorations") == []
    assert target.read_text() == "current B"
