import asyncio
import sys
from pathlib import Path

import aiofiles
import pytest
from fastapi import HTTPException, Request

from app.routers.snapshots import eligible_snapshots
from app.servers.models import Server
from app.snapshots.api_models import CreateSnapshotRequest
from app.snapshots.scopes import PathsScope
from app.utils.exec import exec_command

pytestmark = pytest.mark.binary('restic')


async def test_disconnect_reaps_lookup_process_and_leaves_database_and_next_query_usable(
    case, monkeypatch, tmp_path, db_session_factory,
):
    target = case.data / 'settings.txt'
    target.write_text('source content')
    source = await case.client.backup([target])
    body = CreateSnapshotRequest(scope=PathsScope(server_id='survival', paths=('settings.txt',)))
    messages = asyncio.Queue()
    request = Request({'type': 'http'}, receive=messages.get)
    marker = tmp_path / 'reader.pid'
    script = 'import os,sys,time; from pathlib import Path; Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)'

    async def slow_repository_read():
        await exec_command(sys.executable, '-c', script, str(marker))
        return []

    async def read_pid():
        while True:
            try:
                async with aiofiles.open(marker) as file:
                    value = await file.read()
                if value:
                    return int(value)
            except FileNotFoundError:
                pass
            await asyncio.sleep(0.01)

    with monkeypatch.context() as patch:
        patch.setattr(case.client, 'list_snapshots', slow_repository_read)
        lookup = asyncio.create_task(eligible_snapshots(body, request))
        try:
            pid = await asyncio.wait_for(read_pid(), 10)
            messages.put_nowait({'type': 'http.disconnect'})
            with pytest.raises(HTTPException) as error:
                await asyncio.wait_for(lookup, 5)
            assert error.value.status_code == 499
            assert not Path(f'/proc/{pid}').exists()
        finally:
            if not lookup.done():
                lookup.cancel()
            await asyncio.gather(lookup, return_exceptions=True)

    async with db_session_factory() as session:
        session.add(Server(server_id='after-query'))
        await session.commit()
    result = await eligible_snapshots(body, Request({'type': 'http'}, receive=asyncio.Queue().get))
    assert [row.id for row in result.snapshots] == [source.id]
    assert target.read_text() == 'source content'
    assert not case.tasks.get_all_tasks()
