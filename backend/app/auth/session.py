import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from joserfc import jwt
from joserfc.errors import BadSignatureError, DecodeError
from pydantic import BaseModel, ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp

from ..config import settings
from ..logger import logger
from ..models import User, UserPublic, UserRole
from .jwt_utils import create_access_token, get_token_expiry, key

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


class JwtClaims(BaseModel):
    sub: str
    user_id: int
    username: str
    role: str
    created_at: str
    csrf: str
    exp: datetime


class TokenValidationError(Exception):
    pass


def get_system_user() -> UserPublic:
    return UserPublic(
        id=0,
        username="SYSTEM",
        role=UserRole.OWNER,
        created_at=datetime.now(timezone.utc),
    )


def user_to_public(user: User) -> UserPublic:
    if user.id is None:
        raise ValueError("User ID is missing")
    return UserPublic(
        id=user.id,
        username=user.username,
        role=user.role,
        created_at=user.created_at,
    )


def create_session_token(user: UserPublic) -> tuple[str, str]:
    csrf_token = secrets.token_urlsafe(32)
    jwt_claims = JwtClaims(
        sub=user.username,
        user_id=user.id,
        username=user.username,
        role=user.role.value,
        created_at=user.created_at.isoformat(),
        csrf=csrf_token,
        exp=get_token_expiry(),
    )
    return create_access_token(jwt_claims), csrf_token


def _cookie_max_age_seconds() -> int:
    return settings.jwt.access_token_expire_minutes * 60


def _cookie_samesite() -> Literal["lax", "strict", "none"]:
    return settings.jwt.cookie_samesite


def set_auth_cookies(response: Response, token: str, csrf_token: str) -> None:
    max_age = _cookie_max_age_seconds()
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.jwt.cookie_secure,
        samesite=_cookie_samesite(),
        path=AUTH_COOKIE_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.jwt.cookie_secure,
        samesite=_cookie_samesite(),
        path=CSRF_COOKIE_PATH,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path=AUTH_COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE_NAME, path=CSRF_COOKIE_PATH)


def decode_session_claims(token: str) -> JwtClaims:
    try:
        payload = jwt.decode(token, key, [settings.jwt.algorithm])
    except (BadSignatureError, DecodeError):
        raise TokenValidationError("Could not decode jwt token")
    except Exception as e:
        raise TokenValidationError(f"Unexpected error decoding token: {e}")

    if payload.claims is None:
        raise TokenValidationError("JWT token invalid: missing claims field")

    try:
        jwt_claims = JwtClaims.model_validate(payload.claims)
    except ValidationError as e:
        raise TokenValidationError(f"JWT token invalid: {e}")

    if jwt_claims.exp < datetime.now(timezone.utc):
        raise TokenValidationError("Token expired")

    return jwt_claims


def user_from_claims(jwt_claims: JwtClaims) -> UserPublic:
    return UserPublic(
        id=jwt_claims.user_id,
        username=jwt_claims.username,
        role=UserRole(jwt_claims.role),
        created_at=datetime.fromisoformat(jwt_claims.created_at),
    )


def validate_session_token(token: str) -> tuple[UserPublic, JwtClaims]:
    claims = decode_session_claims(token)
    return user_from_claims(claims), claims


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def is_master_authorization(
    authorization: str | None, master_token: str | None = None
) -> bool:
    return _extract_bearer_token(authorization) == (
        master_token or settings.master_token
    )


def get_user_from_auth_values(
    session_token: str | None,
    authorization: str | None,
    master_token: str | None = None,
) -> UserPublic:
    if is_master_authorization(authorization, master_token):
        logger.info("Master token used; acting as SYSTEM user")
        return get_system_user()

    if session_token:
        user, _ = validate_session_token(session_token)
        return user

    raise TokenValidationError("Not authenticated")


def get_user_from_request(request: HTTPConnection) -> UserPublic:
    return get_user_from_auth_values(
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
            or is_master_authorization(request.headers.get("authorization"))
        ):
            return await call_next(request)

        session_token = request.cookies.get(AUTH_COOKIE_NAME)
        if not session_token:
            return await call_next(request)

        csrf_header = request.headers.get(CSRF_HEADER_NAME)
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        try:
            _, claims = validate_session_token(session_token)
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
