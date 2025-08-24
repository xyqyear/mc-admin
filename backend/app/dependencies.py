from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from joserfc import jwt
from joserfc.errors import BadSignatureError, DecodeError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db.crud.user import get_user_by_username
from .db.database import get_db
from .logger import logger
from .models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


class TokenData(BaseModel):
    username: str


async def get_current_user(
    db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Allow master token to act as a privileged SYSTEM user
    if token == settings.master_token:
        logger.info("Master token used; acting as SYSTEM user")
        return get_system_user()
    token_data: TokenData | None = None
    try:
        payload = jwt.decode(token, settings.jwt.secret_key, [settings.jwt.algorithm])
        claims = payload.claims
        if claims is not None:
            username = cast(str, claims.get("sub"))
            token_data = TokenData(username=username)
    except (BadSignatureError, DecodeError):
        raise credentials_exception

    if token_data is None or token_data.username is None:
        raise credentials_exception

    user = await get_user_by_username(db, token_data.username)

    if user is None:
        raise credentials_exception

    return user


class RequireRole:
    def __init__(self, roles: tuple[UserRole, ...] | UserRole):
        self.roles = roles if isinstance(roles, tuple) else (roles,)

    async def __call__(self, user: User = Depends(get_current_user)):
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


def get_system_user() -> User:
    """Return a synthetic OWNER user representing system actions.

    This user is not persisted to the database and is used when the master token
    is presented in place of a JWT bearer token.
    """
    # Create a User object that won't be persisted
    user = User()
    user.id = 0
    user.username = "SYSTEM"
    user.role = UserRole.OWNER
    user.hashed_password = ""
    return user
