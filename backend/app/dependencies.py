from typing import Annotated, Generator, cast

from config import settings
from db.crud.user import get_user_by_username
from db.database import get_session
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from joserfc import jwt
from joserfc.errors import BadSignatureError, DecodeError
from models import User, UserRole
from pydantic import BaseModel
from sqlmodel import Session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


class TokenData(BaseModel):
    username: str


def get_db() -> Generator[Session, None, None]:
    with get_session() as session:
        yield session


def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt.secret_key, [settings.jwt.algorithm])
        claims = payload.claims
        if claims is not None:
            username = cast(str, claims.get("sub"))
            token_data = TokenData(username=username)
    except (BadSignatureError, DecodeError):
        raise credentials_exception

    if token_data.username is None:
        raise credentials_exception

    user = get_user_by_username(db, token_data.username)

    if user is None:
        raise credentials_exception

    return user


class RequireRole:
    def __init__(self, roles: tuple[UserRole, ...] | UserRole):
        self.roles = roles if isinstance(roles, tuple) else (roles,)

    def __call__(self, user: User = Depends(get_current_user)):
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
