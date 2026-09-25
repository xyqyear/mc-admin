from typing import Annotated

from fastapi import (
    Cookie,
    Depends,
    Header,
    HTTPException,
    WebSocket,
    WebSocketException,
)
from starlette import status

from app.auth.models import UserRole
from app.auth.schemas import UserPublic
from app.auth.service import TokenValidationError, get_identity_service

from .auth.session import (
    AUTH_COOKIE_NAME,
    get_user_from_request,
    verify_websocket_origin,
)
from .config import get_settings


async def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=AUTH_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> UserPublic:
    settings = get_settings()
    try:
        return await get_identity_service().get_user_from_auth_values(session_token, authorization, settings.master_token)
    except TokenValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


class RequireRole:
    def __init__(self, roles: tuple[UserRole, ...] | UserRole):
        self.roles = roles if isinstance(roles, tuple) else (roles,)

    async def __call__(self, user: UserPublic = Depends(get_current_user)):
        if user.role not in self.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return user


def verify_master_token(authorization: Annotated[str | None, Header()] = None):
    settings = get_settings()
    if not get_identity_service().is_master_authorization(authorization, settings.master_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires a master token",
        )


async def get_websocket_user(websocket: WebSocket) -> UserPublic:
    try:
        verify_websocket_origin(websocket)
        return await get_user_from_request(websocket)
    except TokenValidationError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
