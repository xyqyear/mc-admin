from collections.abc import AsyncGenerator

from fastapi import Depends, Request

from app.auth.schemas import UserPublic

from ...config import get_settings
from ...db.database import get_async_session
from ...dependencies import get_current_user
from ...operation_admission import get_server_write_admission
from ...runtime_resources import current_runtime
from ...servers.references import resolve_server_ref


async def _require_registered(server_id: str) -> None:
    settings = get_settings()
    if current_runtime().journal is not None:
        async with get_async_session() as db:
            await resolve_server_ref(db, server_id, servers_root=settings.server_path)


async def admit_server_io(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> AsyncGenerator[None]:
    with get_server_write_admission().write([server_id]):
        await _require_registered(server_id)
        yield


async def admit_server_write(
    request: Request, server_id: str, _: UserPublic = Depends(get_current_user)
) -> AsyncGenerator[None]:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        yield
    else:
        with get_server_write_admission().write([server_id]):
            route = request.scope.get("route")
            creating = request.method == "POST" and getattr(route, "path", None) == "/servers/{server_id}"
            if not creating:
                await _require_registered(server_id)
            yield
