from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from .audit import OperationAuditMiddleware
from .config import settings
from .db.database import init_db
from .routers import admin, archive, auth, snapshots, system, user
from .routers.servers import compose as server_compose
from .routers.servers import console as server_console
from .routers.servers import create as server_create
from .routers.servers import files as server_files
from .routers.servers import misc as server_misc
from .routers.servers import operations as server_operations
from .routers.servers import players as server_players
from .routers.servers import populate as server_populate
from .routers.servers import rcon as server_rcon
from .routers.servers import resources as server_resources


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


api_app = FastAPI(lifespan=lifespan, root_path="/api")

# 添加操作审计中间件（注意顺序：后添加的中间件先执行）
api_app.add_middleware(OperationAuditMiddleware)

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_app.include_router(auth.router)
api_app.include_router(user.router)
api_app.include_router(admin.router)
api_app.include_router(system.router)
api_app.include_router(snapshots.router)
api_app.include_router(archive.router)
api_app.include_router(server_misc.router)
api_app.include_router(server_resources.router)
api_app.include_router(server_players.router)
api_app.include_router(server_compose.router)
api_app.include_router(server_operations.router)
api_app.include_router(server_create.router)
api_app.include_router(server_populate.router)
api_app.include_router(server_console.router)
api_app.include_router(server_rcon.router)
api_app.include_router(server_files.router)

app = FastAPI(title="MC Admin")
app.mount("/api", api_app)
# 外层路径需要放在后面，越先mount的优先级越高。
app.mount("/", StaticFiles(directory=settings.static_path.resolve(), html=True), name="static")
