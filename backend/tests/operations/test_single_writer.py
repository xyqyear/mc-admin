import asyncio
import os
import sys
import threading
from pathlib import Path

import pytest

from app.operations.single_writer import SingleWriterGuard


async def test_database_or_server_root_rejects_a_second_writer(tmp_path):
    database = f"sqlite+aiosqlite:///{tmp_path / 'database.sqlite3'}"
    root = tmp_path / "servers"
    async with SingleWriterGuard(database, root):
        with pytest.raises(RuntimeError, match="单 worker"):
            async with SingleWriterGuard(database, tmp_path / "other-servers"):
                pytest.fail("Shared database admitted a second writer")
        with pytest.raises(RuntimeError, match="单 worker"):
            async with SingleWriterGuard(f"sqlite:///{tmp_path / 'other.sqlite3'}", root):
                pytest.fail("Shared server root admitted a second writer")
    async with SingleWriterGuard(database, root):
        pass


async def test_independent_installations_can_run_concurrently(tmp_path):
    async with (
        SingleWriterGuard(f"sqlite:///{tmp_path / 'one.sqlite3'}", tmp_path / "one"),
        SingleWriterGuard(f"sqlite:///{tmp_path / 'two.sqlite3'}", tmp_path / "two"),
    ):
        assert (tmp_path / "one/.mc-admin-writer.lock").exists()
        assert (tmp_path / "two/.mc-admin-writer.lock").exists()


async def test_kernel_releases_writer_lease_after_process_exit(tmp_path):
    database = f"sqlite:///{tmp_path / 'process.sqlite3'}"
    root = tmp_path / "servers"
    script = """
import asyncio, sys
from pathlib import Path
from app.operations.single_writer import SingleWriterGuard
async def main():
    async with SingleWriterGuard(sys.argv[1], Path(sys.argv[2])):
        print('owned', flush=True)
        await asyncio.Event().wait()
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script, database, str(root),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2])),
    )
    try:
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), 10) == b"owned\n"
        with pytest.raises(RuntimeError, match="单 worker"):
            async with SingleWriterGuard(database, root):
                pytest.fail("Second process entered the installation")
        process.kill()
        await process.wait()
        async with SingleWriterGuard(database, root):
            pass
    finally:
        if process.returncode is None:
            process.kill()
        await process.communicate()


async def test_cancelled_acquisition_waits_for_thread_then_releases_lease(tmp_path, monkeypatch):
    database = f"sqlite:///{tmp_path / 'cancel.sqlite3'}"
    root = tmp_path / "servers"
    guard = SingleWriterGuard(database, root)
    acquired = asyncio.Event()
    release_thread = threading.Event()
    loop = asyncio.get_running_loop()
    original = guard._acquire

    def delayed_acquire():
        original()
        loop.call_soon_threadsafe(acquired.set)
        if not release_thread.wait(5):
            raise RuntimeError("Test did not release its acquisition barrier")

    monkeypatch.setattr(guard, "_acquire", delayed_acquire)
    task = asyncio.create_task(guard.__aenter__())
    try:
        await asyncio.wait_for(acquired.wait(), 5)
        task.cancel()
        with pytest.raises(RuntimeError, match="单 worker"):
            async with SingleWriterGuard(database, root):
                pytest.fail("Pending acquisition released its kernel lease too early")
    finally:
        release_thread.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
    async with SingleWriterGuard(database, root):
        pass
