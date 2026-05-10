from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from joserfc import jwt
from joserfc.errors import BadSignatureError, DecodeError
from pydantic import BaseModel, ValidationError

from .auth.jwt_utils import key
from .config import settings
from .logger import logger
from .models import UserPublic, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


class JwtClaims(BaseModel):
    sub: str
    user_id: int
    username: str
    role: str
    created_at: str
    exp: datetime


class TokenValidationError(Exception):
    pass


def _validate_token_and_get_user(token: str) -> UserPublic:
    """Validate a token (master or JWT) and return the corresponding user."""
    if token == settings.master_token:
        logger.info("Master token used; acting as SYSTEM user")
        return get_system_user()

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

    return UserPublic(
        id=jwt_claims.user_id,
        username=jwt_claims.username,
        role=UserRole(jwt_claims.role),
        created_at=datetime.fromisoformat(jwt_claims.created_at),
    )


def get_current_user(token: str = Depends(oauth2_scheme)) -> UserPublic:
    try:
        return _validate_token_and_get_user(token)
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
                status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
            )
        return user


def verify_master_token(authorization: Annotated[str, Header()]):
    given_token = authorization.split(" ")[1]
    if given_token != settings.master_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires a master token",
        )


def get_websocket_user(token: Annotated[str | None, Query()] = None) -> UserPublic:
    """Validate a JWT token from query parameter for WebSocket connections."""
    if token is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    try:
        return _validate_token_and_get_user(token)
    except TokenValidationError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)


def get_system_user() -> UserPublic:
    """Synthetic OWNER user used when the master token is presented; not persisted."""
    return UserPublic(
        id=0, username="SYSTEM", role=UserRole.OWNER, created_at=datetime.now()
    )
