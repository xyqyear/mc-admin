import asyncio
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2 as httpx
import pytest
from fastapi import HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from joserfc import jwt
from joserfc.errors import BadSignatureError
from sqlalchemy import text

from app.archive.uploads import ArchiveUploadInitRequest, init_archive_upload
from app.audit import get_audit_logger
from app.auth.service import get_identity_service
from app.background_tasks import get_task_manager
from app.background_tasks.types import TaskProgress, TaskStatus, TaskType
from app.chunk_prune.models import ChunkPruneTaskMetadata
from app.config import JWTSettings, Settings, get_settings
from app.db.database import get_async_session
from app.dynamic_config import get_config, get_config_manager
from app.events.bus import get_event_bus
from app.events.models import HeartbeatFrame
from app.logger import get_logger
from app.main import create_app
from app.operation_admission import get_server_write_admission
from app.operations.context import OperationExecution, bind_execution, current_execution
from app.operations.journal import OperationJournal
from app.operations.journal_types import ProcessIdentity
from app.operations.single_writer import SingleWriterGuard
from app.runtime import Runtime, RuntimeHooks
from app.runtime_resources import current_runtime, spawn_background
from app.world.preview import PreviewSessionManager


def make_runtime(tmp_path: Path, name: str, *, hooks: RuntimeHooks | None = None, **overrides) -> Runtime:
    root = tmp_path / name
    for directory in ("servers", "archives", "logs", "static/static", "static/assets"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "static/index.html").write_text(f"<html>{name}</html>")
    return Runtime(Settings(  # type: ignore
        server_path=root / "servers", archive_path=root / "archives", logs_dir=root / "logs",
        static_path=root / "static", database_url=f"sqlite+aiosqlite:///{root / 'app.sqlite3'}",
        jwt=JWTSettings(secret_key=f"{name}-synthetic-jwt-secret-{'x' * 32}"), restic=None,
    ), overrides=overrides, hooks=hooks)


async def test_two_running_apps_own_database_configuration_auth_events_and_tasks(tmp_path):
    first, second = make_runtime(tmp_path, "first"), make_runtime(tmp_path, "second")
    apps = [create_app(runtime=runtime) for runtime in (first, second)]
    seen = []
    writers_started = [asyncio.Event(), asyncio.Event()]
    writers_stopped = [asyncio.Event(), asyncio.Event()]
    task_ids = []

    async def writer(index):
        try:
            writers_started[index].set()
            yield TaskProgress(message="owned writer")
            await asyncio.Event().wait()
        finally:
            writers_stopped[index].set()

    async def probe():
        async with get_async_session() as db:
            value = await db.scalar(text("SELECT value FROM runtime_probe"))
        get_event_bus().publish(HeartbeatFrame(timestamp=datetime.now(UTC)))
        async def child():
            seen.append(current_runtime())
        await spawn_background(child(), name="runtime-probe")
        return {"value": value, "root": str(get_settings().server_path), "ttl": get_config().dns.dns_ttl}

    for app in apps:
        app.state.api_app.get("/runtime-probe")(probe)
    try:
        for index, runtime in enumerate((first, second)):
            await runtime.start()
            with runtime.bind():
                async with get_async_session() as db:
                    await db.execute(text("CREATE TABLE runtime_probe (value TEXT)"))
                    await db.execute(text("INSERT INTO runtime_probe VALUES (:value)"), {"value": str(index)})
                    await db.commit()
                await get_config_manager().update_config("dns", {"dns_ttl": index + 20})
                submission = await get_task_manager().submit_durable(TaskType.ARCHIVE_CREATE, "owned writer", writer(index))
                task_ids.append(submission.task_id)
        await asyncio.gather(*(started.wait() for started in writers_started))
        assert first.resource("task_manager").get_task(task_ids[1]) is None
        assert second.resource("task_manager").get_task(task_ids[0]) is None
        subscriptions = [runtime.resource("event_bus").subscribe() for runtime in (first, second)]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[0]), base_url="http://first") as a, httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[1]), base_url="http://second") as b:
            responses = await asyncio.gather(a.get("/api/runtime-probe"), b.get("/api/runtime-probe"))
        assert [r.status_code for r in responses] == [200, 200]
        assert [r.json()["value"] for r in responses] == ["0", "1"]
        assert [r.json()["ttl"] for r in responses] == [20, 21]
        assert {r.json()["root"] for r in responses} == {str(first.settings.server_path), str(second.settings.server_path)}
        assert set(seen) == {first, second}
        assert all(subscription.queue.qsize() == 1 for subscription in subscriptions)
        for name in ("task_manager", "event_bus", "config_manager", "cron_manager", "dns_manager", "database", "login_code_manager", "chunk_prune_service"):
            assert first.resource(name) is not second.resource(name)
        with first.bind():
            token = jwt.encode({"alg": "HS256"}, {"exp": (datetime.now(UTC) + timedelta(minutes=1)).timestamp()}, get_identity_service().signing_key)
        with second.bind(), pytest.raises(BadSignatureError):
            jwt.decode(token, get_identity_service().signing_key, ["HS256"])
        for name, runtime in (("first", first), ("second", second)):
            with runtime.bind():
                get_logger().info("owned application log: %s", name)
                audit_logger = get_audit_logger()
                assert audit_logger is not None
                audit_logger.info("owned audit log: %s", name)
        await first.close()
        assert writers_stopped[0].is_set()
        assert not writers_stopped[1].is_set()
        assert first.resource("task_manager").get_task(task_ids[0]).status is TaskStatus.CANCELLED
        assert subscriptions[0].lagged
        assert not subscriptions[1].lagged
        assert second.resource("cron_manager").scheduler.running
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[1]), base_url="http://second") as client:
            assert (await client.get("/api/runtime-probe")).status_code == 200
    finally:
        await first.close()
        await second.close()
    assert all(runtime.closed and not runtime.requests for runtime in (first, second))
    assert writers_stopped[1].is_set()
    assert all(not runtime.resource("cron_manager").scheduler.running for runtime in (first, second))
    for name, other, runtime in (("first", "second", first), ("second", "first", second)):
        application_log = (runtime.settings.logs_dir / "app.log").read_text()
        operation_log = (runtime.settings.logs_dir / "operations.log").read_text()
        assert f"owned application log: {name}" in application_log
        assert f"owned application log: {other}" not in application_log
        assert f"owned audit log: {name}" in operation_log
        assert f"owned audit log: {other}" not in operation_log
        assert not runtime.resource("app_logger").handlers
        assert not runtime.resource("audit_logger").handlers


@pytest.mark.parametrize("stage", ["migrate", "config", "recover", "prune", "previews", "players", "cron", "janitor"])
async def test_partial_startup_closes_acquired_resources_and_releases_writer_guard(tmp_path, monkeypatch, stage):
    steps = []
    runtime = make_runtime(tmp_path, stage)

    async def execute(name):
        assert runtime is current_runtime()
        with pytest.raises(HTTPException) as unavailable:
            get_server_write_admission().check("owned-server")
        assert unavailable.value.status_code == 503
        steps.append(name)
        if name == stage:
            raise RuntimeError(f"failure at {name}")

    runtime.hooks = RuntimeHooks(migrate=lambda: execute("migrate"), recover=lambda _: execute("recover"))
    database = SimpleNamespace(close=AsyncMock())
    configuration = SimpleNamespace(initialize_all_configs=lambda: execute("config"))
    dns = SimpleNamespace(initialize=lambda: execute("dns"), is_initialized=False, close=AsyncMock())
    cron = SimpleNamespace(initialize=lambda: execute("cron"), shutdown=AsyncMock())
    world = SimpleNamespace(prepare=lambda: execute("previews"), close=AsyncMock())
    prune = SimpleNamespace(start=lambda: execute("prune"), close=AsyncMock())
    def start_janitor():
        steps.append("janitor")
        if stage == "janitor":
            raise RuntimeError("failure at janitor")
    world.start_janitor = start_janitor
    runtime.resources.update(database=database, config_manager=configuration, dns_manager=dns, cron_manager=cron, world_restore_orchestrator=world, chunk_prune_service=prune)
    monkeypatch.setattr("app.players.start_player_system", lambda: execute("players"))
    with pytest.raises(RuntimeError, match=f"failure at {stage}"):
        await runtime.start()
    assert runtime.closed and not runtime.started
    assert steps == ["migrate", "config", "recover", "prune", "previews", "dns", "players", "cron", "janitor"][:steps.index(stage) + 1]
    for closer in (database.close, dns.close, cron.shutdown, world.close, prune.close):
        closer.assert_awaited_once()
    async with SingleWriterGuard(runtime.settings.database_url, runtime.settings.server_path):
        pass


async def test_shutdown_drains_producers_and_writers_before_clients_even_when_repeatedly_cancelled(tmp_path):
    order = []
    writer_started, writer_cleanup, allow_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def writer():
        writer_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            writer_cleanup.set()
            await allow_cleanup.wait()
            order.append("writer")
    async def close_resource(name):
        order.append(name)
    runtime = make_runtime(tmp_path, "cancel", database=SimpleNamespace(close=lambda: close_resource("database")), cron_manager=SimpleNamespace(shutdown=lambda: close_resource("cron")), dns_manager=SimpleNamespace(close=lambda: close_resource("dns")))
    child = runtime.spawn(writer(), name="owned-writer")
    await writer_started.wait()
    closer = asyncio.create_task(runtime.close())
    await writer_cleanup.wait()
    closer.cancel()
    await asyncio.sleep(0)
    closer.cancel()
    assert order == ["cron"]
    allow_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await closer
    assert child.done() and runtime.closed
    assert order == ["cron", "writer", "dns", "database"]


async def test_shutdown_continues_after_client_close_failure_and_removes_owned_scratch(tmp_path):
    database = SimpleNamespace(close=AsyncMock())
    runtime = make_runtime(tmp_path, "close-error", database=database, dns_manager=SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("synthetic close failure"))))
    scratch = runtime.scratch_dir
    (scratch / "preview").write_text("owned")
    with pytest.raises(RuntimeError, match="synthetic close failure"):
        await runtime.close()
    database.close.assert_awaited_once()
    assert runtime.closed and not scratch.exists()


async def test_websocket_context_is_bound_through_disconnect_and_shutdown_refuses_new_requests(tmp_path):
    runtime = make_runtime(tmp_path, "websocket")
    app = create_app(runtime=runtime)
    observed = []
    @app.state.api_app.websocket("/runtime-websocket")
    async def socket(websocket: WebSocket):
        observed.append(current_runtime())
        await websocket.accept()
        await websocket.receive_text()
        observed.append(current_runtime())
        await websocket.close()
    messages = asyncio.Queue()
    for message in ({"type": "websocket.connect"}, {"type": "websocket.receive", "text": "finish"}):
        messages.put_nowait(message)
    outgoing = []
    async def send(message):
        outgoing.append(message)
    await app({"type": "websocket", "path": "/api/runtime-websocket", "raw_path": b"/api/runtime-websocket", "root_path": "", "scheme": "ws", "query_string": b"", "headers": [], "client": ("127.0.0.1", 1), "server": ("test", 80), "subprotocols": []}, messages.get, send)
    assert observed == [runtime, runtime]
    assert outgoing[-1]["type"] == "websocket.close"
    assert not runtime.requests
    await runtime.close()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/system/info")).status_code == 503


async def test_shutdown_cancels_and_drains_stream_before_database_close(tmp_path):
    streamed, cleaned = asyncio.Event(), asyncio.Event()
    observations = []
    async def database_close():
        assert cleaned.is_set()
    runtime = make_runtime(tmp_path, "sse", database=SimpleNamespace(close=database_close))
    app = create_app(runtime=runtime)
    async def body():
        try:
            observations.append(current_runtime())
            yield "data: owned\n\n"
            streamed.set()
            await asyncio.Event().wait()
        finally:
            observations.append(current_runtime())
            cleaned.set()
    @app.state.api_app.get("/runtime-stream")
    async def stream():
        return StreamingResponse(body(), media_type="text/event-stream")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    request = asyncio.create_task(client.get("/api/runtime-stream"))
    try:
        await streamed.wait()
        assert not request.done()
        await runtime.close()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert observations == [runtime, runtime]
        assert cleaned.is_set() and not runtime.requests
    finally:
        await client.aclose()
        await runtime.close()


async def test_detached_work_and_new_requests_do_not_inherit_parent_operation(tmp_path):
    parent_runtime, request_runtime = make_runtime(tmp_path, "parent"), make_runtime(tmp_path, "request")
    execution = OperationExecution(OperationJournal(parent_runtime.database.session_factory), "parent-operation")
    app = create_app(runtime=request_runtime)
    async def inspect_context():
        return current_runtime(), current_execution()
    @app.state.api_app.get("/runtime-parent")
    async def endpoint():
        runtime, parent = await inspect_context()
        assert runtime is request_runtime
        return {"operation": parent.operation_id if parent else None}
    try:
        with parent_runtime.bind(), bind_execution(execution):
            child_runtime, child_execution = await spawn_background(inspect_context(), name="detached-check")
            assert child_runtime is parent_runtime
            assert child_execution is None
            assert current_execution() is execution
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/runtime-parent")
            assert response.status_code == 200
            assert response.json() == {"operation": None}
            assert current_execution() is execution
    finally:
        await parent_runtime.close()
        await request_runtime.close()


async def test_two_apps_can_start_concurrently_with_independent_migrations(tmp_path):
    first, second = make_runtime(tmp_path, "concurrent-first"), make_runtime(tmp_path, "concurrent-second")
    try:
        results = await asyncio.gather(first.start(), second.start(), return_exceptions=True)
        assert results == [None, None]
        assert first.started and second.started
        for runtime in (first, second):
            async with runtime.database.session_factory() as session:
                assert await session.scalar(text("SELECT COUNT(*) FROM alembic_version")) == 1
    finally:
        await first.close()
        await second.close()


async def test_cancelled_startup_keeps_writer_guard_until_migration_thread_finishes(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path, "migration-cancel")
    entered, release = threading.Event(), threading.Event()
    migration_finished = []
    def migrate():
        entered.set()
        assert release.wait(5)
        migration_finished.append(True)
    monkeypatch.setattr("app.db.migrations._migrate_owned_database", migrate)
    starter = asyncio.create_task(runtime.start())
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        starter.cancel()
        await asyncio.sleep(0)
        assert not starter.done()
        with pytest.raises(RuntimeError, match="已有后端写入进程"):
            async with SingleWriterGuard(runtime.settings.database_url, runtime.settings.server_path):
                pytest.fail("Migration writer lease was released early")
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await starter
        await runtime.close()
    assert migration_finished == [True]
    assert runtime.closed
    async with SingleWriterGuard(runtime.settings.database_url, runtime.settings.server_path):
        pass


@pytest.mark.parametrize("evidence", ["process", "unknown_ownership", "unreadable_journal"])
async def test_shutdown_preserves_artifacts_for_unconfirmed_writers_and_still_closes_clients(tmp_path, evidence):
    runtime = make_runtime(tmp_path, evidence)
    await runtime.start()
    assert runtime.journal is not None
    started = asyncio.Event()
    async def writer():
        execution = current_execution()
        assert execution is not None
        if evidence == "process":
            await execution.journal.register_process(execution.operation_id, ProcessIdentity(
                pid=12345, pgid=12345, start_ticks=1, boot_id="synthetic-boot", root_dev=1, root_ino=1,
            ))
        elif evidence == "unknown_ownership":
            await execution.journal.set_ownership_known(execution.operation_id, False)
        started.set()
        yield TaskProgress(message="writer awaiting cancellation")
        await asyncio.Event().wait()
    scratch = runtime.scratch_dir
    upload_path = None
    try:
        with runtime.bind():
            prune = runtime.resource("chunk_prune_service")
            claims = scratch / "claims.json"
            claims.write_text("{}")
            prune._metadata["preserved"] = ChunkPruneTaskMetadata(
                task_id="preserved", server_id="synthetic", operation="preview",
                data_path=runtime.settings.server_path, threshold_seconds=1,
                threshold_ticks=20, mode="chunks", claims_file=claims,
            )
            previews = PreviewSessionManager(base_dir=scratch / "previews")
            preview = await previews.create_session("synthetic")
            queue = AsyncMock()
            previews.attach_render_queue(preview.name, queue=queue, affected_keys=set())
            previews.start_janitor()
            runtime.resources["world_restore_orchestrator"] = previews
            upload = await init_archive_upload(runtime.settings.archive_path, ArchiveUploadInitRequest(filename="owned.zip", size=1))
            upload_path = runtime.resource("archive_upload_sessions")[upload.upload_id].temp_path
            database_close = AsyncMock(wraps=runtime.database.close)
            runtime.database.close = database_close
            dns_close = AsyncMock(wraps=runtime.resource("dns_manager").close)
            runtime.resource("dns_manager").close = dns_close
            submitted = await get_task_manager().submit_durable(TaskType.ARCHIVE_CREATE, "unconfirmed writer", writer())
        await started.wait()
        if evidence == "unreadable_journal":
            runtime.journal.unsettled = AsyncMock(side_effect=OSError("synthetic journal failure"))
        with pytest.raises(RuntimeError, match="已保留临时产物"):
            await runtime.close()
        assert runtime.closed
        assert claims.exists() and preview.is_dir() and upload_path.exists()
        assert "preserved" in prune._metadata
        assert previews._janitor_task is None
        queue.close.assert_awaited_once()
        database_close.assert_awaited_once()
        dns_close.assert_awaited_once()
        assert submitted.awaitable.done()
        if evidence != "unreadable_journal":
            assert submitted.task.status is TaskStatus.FAILED
    finally:
        if not runtime.closed:
            await runtime.close()
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)
        shutil.rmtree(scratch, ignore_errors=True)


@pytest.mark.parametrize("failure", ["initialize", "update", None])
async def test_optional_dns_failure_does_not_prevent_local_startup(tmp_path, monkeypatch, failure):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session():
        yield object()

    dns = SimpleNamespace(initialize=AsyncMock(), update=AsyncMock(), is_initialized=False, close=AsyncMock())
    if failure:
        getattr(dns, failure).side_effect = RuntimeError("private-provider-credential")
    cron = SimpleNamespace(initialize=AsyncMock(), shutdown=AsyncMock())
    database = SimpleNamespace(session_factory=session, close=AsyncMock())
    runtime = make_runtime(
        tmp_path, f"optional-{failure}", database=database,
        hooks=RuntimeHooks(migrate=AsyncMock(), recover=AsyncMock()),
        config_manager=SimpleNamespace(initialize_all_configs=AsyncMock()),
        dns_manager=dns, cron_manager=cron, world_restore_orchestrator=None,
        chunk_prune_service=SimpleNamespace(start=AsyncMock(), close=AsyncMock()),
    )
    players = AsyncMock()
    monkeypatch.setattr("app.players.start_player_system", players)
    try:
        await runtime.start()
        assert runtime.started and not runtime.closed
        players.assert_awaited_once()
        cron.initialize.assert_awaited_once()
        if failure != "initialize":
            dns.update.assert_awaited_once()
        with runtime.bind():
            get_server_write_admission().check("owned-server")
    finally:
        await runtime.close()
    dns.close.assert_awaited_once()
    database.close.assert_awaited_once()
    if failure:
        assert "private-provider-credential" not in (runtime.settings.logs_dir / "app.log").read_text()


async def test_runtime_access_without_binding_cannot_create_an_implicit_application():
    from contextvars import Context

    from app.runtime_resources import bound_runtime

    context = Context()
    assert context.run(bound_runtime) is None
    with pytest.raises(RuntimeError, match="No application runtime"):
        context.run(current_runtime)
    with pytest.raises(RuntimeError, match="No application runtime"):
        context.run(get_settings)
