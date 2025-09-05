from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from joserfc import jwt
from joserfc.errors import BadSignatureError, DecodeError
from pydantic import BaseModel

from .auth.jwt_utils import key
from .config import settings
from .logger import logger
from .models import UserPublic, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


class JwtClaims(BaseModel):
    sub: str  # username
    user_id: int
    username: str
    role: str
    created_at: str
    exp: datetime  # expiration time


def get_current_user(token: str = Depends(oauth2_scheme)) -> UserPublic:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Allow master token to act as a privileged SYSTEM user
    if token == settings.master_token:
        logger.info("Master token used; acting as SYSTEM user")
        return get_system_user()

    try:
        payload = jwt.decode(token, key, [settings.jwt.algorithm])
        if payload.claims is not None:
            # 使用 Pydantic 模型解析 JWT claims
            jwt_claims = JwtClaims.model_validate(payload.claims)

            # 检查过期时间
            if jwt_claims.exp < datetime.now(timezone.utc):
                raise credentials_exception

            return UserPublic(
                id=jwt_claims.user_id,
                username=jwt_claims.username,
                role=UserRole(jwt_claims.role),
                created_at=datetime.fromisoformat(jwt_claims.created_at),
            )

    except (BadSignatureError, DecodeError, ValueError):
        raise credentials_exception

    raise credentials_exception


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
    """
    WebSocket authentication dependency.
    Extracts JWT token from query parameter and validates it.
    Note: WebSocket parameter should not be included in dependencies.
    """
    if token is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    # Allow master token to act as a privileged SYSTEM user
    if token == settings.master_token:
        logger.info("Master token used via WebSocket; acting as SYSTEM user")
        return get_system_user()

    try:
        payload = jwt.decode(token, key, [settings.jwt.algorithm])
        if payload.claims is not None:
            # 使用 Pydantic 模型解析 JWT claims
            jwt_claims = JwtClaims.model_validate(payload.claims)

            # 检查过期时间
            if jwt_claims.exp < datetime.now(timezone.utc):
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

            return UserPublic(
                id=jwt_claims.user_id,
                username=jwt_claims.username,
                role=UserRole(jwt_claims.role),
                created_at=datetime.fromisoformat(jwt_claims.created_at),
            )
    except (BadSignatureError, DecodeError, ValueError):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)


def get_system_user() -> UserPublic:
    """Return a synthetic OWNER user representing system actions.

    This user is not persisted to the database and is used when the master token
    is presented in place of a JWT bearer token.
    """
    return UserPublic(
        id=0, username="SYSTEM", role=UserRole.OWNER, created_at=datetime.now()
    )
