from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from .audit import OperationAuditMiddleware
from .db.database import init_db
from .routers import admin, auth, system, user
from .routers.servers import console, files, misc, rcon, snapshots


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan, root_path="/api")

# 添加操作审计中间件（注意顺序：后添加的中间件先执行）
app.add_middleware(OperationAuditMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(system.router)
app.include_router(misc.router)
app.include_router(console.router)
app.include_router(rcon.router)
app.include_router(files.router)
app.include_router(snapshots.router)
