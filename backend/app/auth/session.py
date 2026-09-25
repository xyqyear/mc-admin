from typing import Literal

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp

from app.auth.schemas import UserPublic

from .service import TokenValidationError, get_identity_service

AUTH_COOKIE_NAME = "mc_admin_session"
CSRF_COOKIE_NAME = "mc_admin_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
AUTH_COOKIE_PATH = "/api"
CSRF_COOKIE_PATH = "/"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
CSRF_EXEMPT_PATHS = {
    "/auth/token",
    "/auth/logout",
    "/auth/verifyCode",
    "/auth/code/complete",
    "/api/auth/token",
    "/api/auth/logout",
    "/api/auth/verifyCode",
    "/api/auth/code/complete",
}
DEV_WEBSOCKET_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}












def _cookie_max_age_seconds() -> int:
    return get_identity_service().settings.jwt.access_token_expire_minutes * 60


def _cookie_samesite() -> Literal["lax", "strict", "none"]:
    return get_identity_service().settings.jwt.cookie_samesite


def set_auth_cookies(response: Response, token: str, csrf_token: str) -> None:
    max_age = _cookie_max_age_seconds()
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        secure=get_identity_service().settings.jwt.cookie_secure,
        samesite=_cookie_samesite(),
        path=AUTH_COOKIE_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=get_identity_service().settings.jwt.cookie_secure,
        samesite=_cookie_samesite(),
        path=CSRF_COOKIE_PATH,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path=AUTH_COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE_NAME, path=CSRF_COOKIE_PATH)
















async def get_user_from_request(request: HTTPConnection) -> UserPublic:
    return await get_identity_service().get_user_from_auth_values(
        request.cookies.get(AUTH_COOKIE_NAME),
        request.headers.get("authorization"),
    )


def websocket_allowed_origins(request: HTTPConnection) -> set[str]:
    origins = set(DEV_WEBSOCKET_ORIGINS)
    hosts = {
        request.headers.get("host"),
        request.headers.get("x-forwarded-host"),
    }
    for host in {h for h in hosts if h}:
        origins.add(f"http://{host}")
        origins.add(f"https://{host}")
    return origins


def verify_websocket_origin(request: HTTPConnection) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin not in websocket_allowed_origins(request):
        raise TokenValidationError("Invalid WebSocket origin")


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        root_path = request.scope.get("root_path") or ""
        path = request.url.path
        scope_path = request.scope.get("path", path)
        candidate_paths = {path, scope_path}
        if root_path and scope_path.startswith(root_path):
            candidate_paths.add(scope_path.removeprefix(root_path))

        if (
            request.method.upper() in SAFE_METHODS
            or bool(candidate_paths & CSRF_EXEMPT_PATHS)
            or get_identity_service().is_master_authorization(request.headers.get("authorization"))
        ):
            return await call_next(request)

        session_token = request.cookies.get(AUTH_COOKIE_NAME)
        if not session_token:
            return await call_next(request)

        csrf_header = request.headers.get(CSRF_HEADER_NAME)
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        try:
            _, claims = get_identity_service().validate_session_token(session_token)
        except TokenValidationError as e:
            return JSONResponse(status_code=401, content={"detail": str(e)})

        if not csrf_header or not csrf_cookie:
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing CSRF token"},
            )
        if csrf_header != csrf_cookie or csrf_header != claims.csrf:
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid CSRF token"},
            )

        return await call_next(request)
