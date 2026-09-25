from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import aiofiles
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware

from .api_schema import preserve_public_schema_names
from .audit import OperationAuditMiddleware
from .auth.session import CSRFMiddleware
from .config import Settings
from .errors import SafeErrorMiddleware
from .routers import (
    admin,
    archive,
    auth,
    cron,
    dns,
    events,
    operations,
    self_check,
    snapshots,
    system,
    tasks,
    user,
)
from .routers import (
    templates as template_routes,
)
from .routers.config import router as config_router
from .routers.players import (
    achievements,
    chat,
    players,
    sessions,
)
from .routers.servers import chunk_prune as server_chunk_prune
from .routers.servers import compose as server_compose
from .routers.servers import console as server_console
from .routers.servers import create as server_create
from .routers.servers import files as server_files
from .routers.servers import map as server_map
from .routers.servers import misc as server_misc
from .routers.servers import operations as server_operations
from .routers.servers import populate as server_populate
from .routers.servers import rcon as server_rcon
from .routers.servers import resources as server_resources
from .routers.servers import restart_schedule as server_restart_schedule
from .routers.servers import sync as server_sync
from .routers.servers import template_config as server_template_config
from .routers.servers import template_migration as server_template_migration
from .routers.servers import world_restore as server_world_restore
from .runtime import Runtime
from .runtime_http import RuntimeMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with app.state.runtime.lifespan():
        yield


def create_api_app(runtime: Runtime) -> FastAPI:
    with runtime.bind():
        api_app = FastAPI(root_path="/api")
        api_app.state.runtime = runtime

        # Middlewares execute in reverse-added order, so audit runs first.
        api_app.add_middleware(OperationAuditMiddleware)
        api_app.add_middleware(CSRFMiddleware)

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
        api_app.add_middleware(SafeErrorMiddleware)

        api_app.include_router(auth.router)
        api_app.include_router(user.router)
        api_app.include_router(admin.router)
        api_app.include_router(system.router)
        api_app.include_router(snapshots.router)
        api_app.include_router(archive.router)
        api_app.include_router(cron.router)
        api_app.include_router(self_check.router)
        api_app.include_router(dns.router)
        api_app.include_router(config_router)
        api_app.include_router(tasks.router)
        api_app.include_router(operations.router)
        api_app.include_router(template_routes.router)
        api_app.include_router(events.router)

        api_app.include_router(players.router)
        api_app.include_router(sessions.router)
        api_app.include_router(sessions.server_router)
        api_app.include_router(chat.router)
        api_app.include_router(achievements.router)

        api_app.include_router(server_misc.router)
        api_app.include_router(server_resources.router)
        api_app.include_router(server_compose.router)
        api_app.include_router(server_operations.router)
        api_app.include_router(server_rcon.router)
        # server_sync must be registered before server_create so POST /servers/sync
        # matches before the catch-all POST /servers/{server_id}.
        api_app.include_router(server_sync.router)
        api_app.include_router(server_create.router)
        api_app.include_router(server_populate.router)
        api_app.include_router(server_console.router)
        api_app.include_router(server_files.router)
        api_app.include_router(server_map.router)
        api_app.include_router(server_chunk_prune.router)
        api_app.include_router(server_restart_schedule.router)
        api_app.include_router(server_template_config.router)
        api_app.include_router(server_template_migration.router)
        api_app.include_router(server_world_restore.router)


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
        api_app.add_middleware(RuntimeMiddleware, runtime=runtime)
        preserve_public_schema_names(api_app)
        return api_app


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None) -> FastAPI:
    if runtime is not None and settings is not None:
        raise ValueError("Provide settings or a runtime, not both")
    runtime = runtime or Runtime(settings)
    settings = runtime.settings
    with runtime.bind():
        app = FastAPI(lifespan=lifespan, title="MC Admin")
        api_app = create_api_app(runtime)
        app.state.runtime = runtime
        app.state.api_app = api_app
        app.add_middleware(RuntimeMiddleware, runtime=runtime)
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


        spa_templates = Jinja2Templates(directory=settings.static_path.resolve())


        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            return spa_templates.TemplateResponse(request=request, name="index.html")

        return app


app = create_app()
api_app: FastAPI = app.state.api_app
