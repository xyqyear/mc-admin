import secrets
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta

from joserfc import jwt
from joserfc.errors import BadSignatureError, DecodeError
from joserfc.jwk import OctKey
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..logger import get_logger
from ..runtime_resources import current_runtime
from .models import User, UserRole
from .schemas import UserPublic


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
    return UserPublic(id=0, username="SYSTEM", role=UserRole.OWNER, created_at=datetime.now(UTC))


def user_to_public(user: User) -> UserPublic:
    if user.id is None:
        raise ValueError("User ID is missing")
    return UserPublic(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


def user_from_claims(claims: JwtClaims) -> UserPublic:
    return UserPublic(
        id=claims.user_id, username=claims.username, role=UserRole(claims.role),
        created_at=datetime.fromisoformat(claims.created_at),
    )


class IdentityService:
    def __init__(
        self, *, settings: Settings,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.clock = clock
        self.signing_key = OctKey.import_key(settings.jwt.secret_key)

    def create_session_token(self, user: UserPublic) -> tuple[str, str]:
        csrf_token = secrets.token_urlsafe(32)
        claims = JwtClaims(
            sub=user.username, user_id=user.id, username=user.username,
            role=user.role.value, created_at=user.created_at.isoformat(), csrf=csrf_token,
            exp=self.clock() + timedelta(minutes=self.settings.jwt.access_token_expire_minutes),
        ).model_dump()
        claims["exp"] = claims["exp"].timestamp()
        token = jwt.encode({"alg": self.settings.jwt.algorithm}, claims, self.signing_key)
        return token, csrf_token

    def decode_session_claims(self, token: str) -> JwtClaims:
        try:
            payload = jwt.decode(token, self.signing_key, [self.settings.jwt.algorithm])
        except (BadSignatureError, DecodeError) as error:
            raise TokenValidationError("Could not decode jwt token") from error
        except Exception as error:
            raise TokenValidationError("无法验证登录会话") from error
        if payload.claims is None:
            raise TokenValidationError("JWT token invalid: missing claims field")
        try:
            claims = JwtClaims.model_validate(payload.claims)
        except ValidationError as error:
            raise TokenValidationError("登录会话内容无效") from error
        if claims.exp < self.clock():
            raise TokenValidationError("Token expired")
        return claims

    def validate_session_token(self, token: str) -> tuple[UserPublic, JwtClaims]:
        claims = self.decode_session_claims(token)
        return user_from_claims(claims), claims

    def is_master_authorization(self, authorization: str | None, master_token: str | None = None) -> bool:
        if not authorization:
            return False
        scheme, _, token = authorization.partition(" ")
        return scheme.lower() == "bearer" and bool(token) and token == (master_token or self.settings.master_token)

    async def get_user_from_auth_values(
        self, session_token: str | None, authorization: str | None,
        master_token: str | None = None,
    ) -> UserPublic:
        logger = get_logger()
        if self.is_master_authorization(authorization, master_token):
            logger.info("Master token used; acting as SYSTEM user")
            return get_system_user()
        if session_token:
            return await self.get_current_session_user(self.decode_session_claims(session_token))
        raise TokenValidationError("Not authenticated")

    async def get_current_session_user(self, claims: JwtClaims) -> UserPublic:
        from .store import get_user_by_id

        async with self.session_factory() as session:
            user = await get_user_by_id(session, claims.user_id)
            if (
                user is None or user.username != claims.username
                or user.created_at != datetime.fromisoformat(claims.created_at)
            ):
                raise TokenValidationError("登录会话对应的用户已不存在")
            return user_to_public(user)


def get_identity_service() -> IdentityService:
    return current_runtime().resource("identity_service")
