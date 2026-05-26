import traceback
from contextlib import asynccontextmanager

import aiofiles
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware

from .audit import OperationAuditMiddleware
from .config import settings
from .cron import cron_manager
from .db.database import get_async_session
from .db.migrations import ensure_database_schema
from .dns import simple_dns_manager
from .dynamic_config import config_manager
from .logger import logger
from .players import start_player_system, stop_player_system
from .routers import (
    admin,
    archive,
    auth,
    cron,
    dns,
    snapshots,
    system,
    tasks,
    templates,
    user,
)
from .routers.config import router as config_router
from .routers.players import (
    achievements,
    chat,
    players,
    sessions,
)
from .routers.servers import compose as server_compose
from .routers.servers import console as server_console
from .routers.servers import create as server_create
from .routers.servers import files as server_files
from .routers.servers import map as server_map
from .routers.servers import misc as server_misc
from .routers.servers import operations as server_operations
from .routers.servers import populate as server_populate
from .routers.servers import resources as server_resources
from .routers.servers import restart_schedule as server_restart_schedule
from .routers.servers import sync as server_sync
from .routers.servers import template_config as server_template_config
from .routers.servers import template_migration as server_template_migration
from .routers.servers import world_restore as server_world_restore
from .world import initialize_world_restore_orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Applying database migrations...")
    await ensure_database_schema()

    logger.info("Initializing dynamic configuration system...")
    await config_manager.initialize_all_configs()

    logger.info("Initializing DNS and router manager module...")
    await simple_dns_manager.initialize()
    if simple_dns_manager.is_initialized:
        async with get_async_session() as db:
            await simple_dns_manager.update(db)

    logger.info("Initializing cron management system...")
    await cron_manager.initialize()

    logger.info("Starting player management system...")
    await start_player_system()

    logger.info("Initializing world-restore orchestrator and crash recovery...")
    interrupted = await server_world_restore.mark_running_restorations_interrupted()
    if interrupted:
        logger.info(
            "World restore crash recovery: %d running restoration(s) marked interrupted",
            interrupted,
        )
    world_restore_orchestrator = initialize_world_restore_orchestrator()
    if world_restore_orchestrator is not None:
        world_restore_orchestrator.start_janitor()
        logger.info("World restore preview janitor started.")
    else:
        logger.info(
            "World restore orchestrator not initialized (restic is not configured)."
        )

    logger.info("Startup complete.")
    yield

    logger.info("Stopping world-restore preview janitor...")
    if world_restore_orchestrator is not None:
        await world_restore_orchestrator.stop_janitor()

    logger.info("Stopping player management system...")
    await stop_player_system()

    logger.info("Shutting down cron management system...")
    await cron_manager.shutdown()


api_app = FastAPI(root_path="/api")

# Middlewares execute in reverse-added order, so audit runs first.
api_app.add_middleware(OperationAuditMiddleware)

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Upload-Offset",
        "Upload-Length",
        "Upload-Chunk-Size",
        "Upload-Expires",
    ],
)

api_app.include_router(auth.router)
api_app.include_router(user.router)
api_app.include_router(admin.router)
api_app.include_router(system.router)
api_app.include_router(snapshots.router)
api_app.include_router(archive.router)
api_app.include_router(cron.router)
api_app.include_router(dns.router)
api_app.include_router(config_router)
api_app.include_router(tasks.router)
api_app.include_router(templates.router)

api_app.include_router(players.router)
api_app.include_router(sessions.router)
api_app.include_router(sessions.server_router)
api_app.include_router(chat.router)
api_app.include_router(achievements.router)

api_app.include_router(server_misc.router)
api_app.include_router(server_resources.router)
api_app.include_router(server_compose.router)
api_app.include_router(server_operations.router)
# server_sync must be registered before server_create so POST /servers/sync
# matches before the catch-all POST /servers/{server_id}.
api_app.include_router(server_sync.router)
api_app.include_router(server_create.router)
api_app.include_router(server_populate.router)
api_app.include_router(server_console.router)
api_app.include_router(server_files.router)
api_app.include_router(server_map.router)
api_app.include_router(server_restart_schedule.router)
api_app.include_router(server_template_config.router)
api_app.include_router(server_template_migration.router)
api_app.include_router(server_world_restore.router)


@api_app.exception_handler(Exception)
async def api_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        logger.info(f"HTTP exception occurred: {exc.detail}")
        return await http_exception_handler(request, exc)
    else:
        logger.error(
            f"Unhandled exception: {exc}, url={request.url}, params={request.query_params} \n {traceback.format_exc(limit=-10)}"
        )
        exc = HTTPException(
            status_code=500,
            detail=f"request to {request.url} failed with error: {str(exc)}",
        )
        return await http_exception_handler(request, exc)


# Flatten Pydantic's verbose error array into a single "detail" string for
# response-format parity with HTTPException.
@api_app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    messages = []
    for error in errors:
        loc = ".".join(str(x) for x in error["loc"] if x != "body")
        msg = error["msg"]
        if loc:
            messages.append(f"{loc}: {msg}")
        else:
            messages.append(msg)
    detail = "; ".join(messages) if messages else "请求参数验证失败"
    return JSONResponse(status_code=422, content={"detail": detail})


app = FastAPI(lifespan=lifespan, title="MC Admin")
app.mount("/api", api_app)

app.mount(
    "/static",
    StaticFiles(directory=(settings.static_path / "static").resolve()),
    name="static",
)
app.mount(
    path="/assets",
    app=StaticFiles(directory=(settings.static_path / "assets").resolve()),
    name="assets",
)


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    async with aiofiles.open(settings.static_path / "robots.txt") as f:
        return await f.read()


templates = Jinja2Templates(directory=settings.static_path.resolve())


@app.get("/{full_path:path}")
async def serve_spa(request: Request, full_path: str):
    return templates.TemplateResponse("index.html", {"request": request})  # type: ignore
