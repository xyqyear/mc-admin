import asyncio
import json
import os
import signal
import socket
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx2 as httpx
from fastapi import FastAPI

from app.auth.schemas import UserPublic
from app.background_tasks import TaskProgress, TaskType
from app.config import Settings
from app.dependencies import get_current_user
from app.main import create_app
from app.runtime import Runtime
from tests.support.environment import isolated_environment


def create_shutdown_app() -> FastAPI:
    root = Path(os.environ["TASK_STREAM_SHUTDOWN_ROOT"])
    runtime = Runtime(Settings(restic=None))  # type: ignore
    application = create_app(runtime=runtime)
    application.state.api_app.dependency_overrides[get_current_user] = lambda: UserPublic(
        id=1, username="shutdown-observer", created_at=datetime.now(UTC),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        ready = asyncio.Event()

        async def worker():
            try:
                yield TaskProgress(progress=25, message="正在执行")
                ready.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.to_thread((root / "worker-cleaned").write_text, "cleaned")

        with runtime.bind():
            accepted = runtime.task_manager.submit(TaskType.ARCHIVE_CREATE, "shutdown-worker", worker())
            try:
                await ready.wait()
                (root / "ready").touch()
                yield
            finally:
                await runtime.close()
                (root / "closed.json").write_text(json.dumps({
                    "closed": runtime.closed,
                    "subscriptions": runtime.task_manager._events.subscriber_count,
                    "requests": len(runtime.requests),
                    "status": accepted.task.status.value,
                    "worker_cleaned": (root / "worker-cleaned").read_text(),
                }))

    application.router.lifespan_context = lifespan
    return application


async def test_image_shutdown_drains_open_task_stream_and_owned_worker(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    dockerfile = (backend.parent / "Dockerfile").read_text()
    command = json.loads(next(line[4:] for line in reversed(dockerfile.splitlines()) if line.startswith("CMD [")))
    assert command[:2] == ["uvicorn", "app.main:app"]
    assert command[command.index("--timeout-graceful-shutdown") + 1] == "2"
    command[1] = "tests.test_task_stream_shutdown:create_shutdown_app"
    environment = {**os.environ, **isolated_environment(tmp_path)}
    environment["TASK_STREAM_SHUTDOWN_ROOT"] = str(tmp_path)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", *command, "--factory", "--fd", str(listener.fileno()),
            pass_fds=(listener.fileno(),), cwd=backend, env=environment,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
    try:
        async with asyncio.timeout(10):
            while not (tmp_path / "ready").exists():
                assert process.returncode is None, "Uvicorn exited before startup"
                await asyncio.sleep(0.01)
        async with (
            httpx.AsyncClient(timeout=5) as client,
            client.stream("GET", f"http://127.0.0.1:{port}/api/tasks/events") as response,
        ):
            assert response.status_code == 200
            lines = response.aiter_lines()
            snapshot = json.loads((await anext(lines))[6:])
            assert snapshot["type"] == "snapshot"
            assert len(snapshot["tasks"]) == 1
            assert snapshot["tasks"][0]["status"] == "running"
            assert snapshot["tasks"][0]["progress"] == 25
            process.send_signal(signal.SIGTERM)
            output, _ = await asyncio.wait_for(process.communicate(), 8)
        assert process.returncode in (0, -signal.SIGTERM), output.decode(errors="replace")
        assert json.loads((tmp_path / "closed.json").read_text()) == {
            "closed": True, "subscriptions": 0, "requests": 0,
            "status": "cancelled", "worker_cleaned": "cleaned",
        }
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()
