from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, WebSocket, WebSocketException
from starlette import status

from .auth.session import (
    AUTH_COOKIE_NAME,
    TokenValidationError,
    get_user_from_auth_values,
    get_user_from_request,
    is_master_authorization,
    verify_websocket_origin,
)
from .config import settings
from .models import UserPublic, UserRole


def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=AUTH_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> UserPublic:
    try:
        return get_user_from_auth_values(session_token, authorization, settings.master_token)
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
    if not is_master_authorization(authorization, settings.master_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires a master token",
        )


def get_websocket_user(websocket: WebSocket) -> UserPublic:
    try:
        verify_websocket_origin(websocket)
        return get_user_from_request(websocket)
    except TokenValidationError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
