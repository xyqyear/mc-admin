from datetime import datetime, timedelta, timezone

from config import settings
from joserfc import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    claims = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            settings.jwt.access_token_expire_minutes
        )
    claims.update({"exp": expire})
    encoded_jwt = jwt.encode(
        header={"alg": settings.jwt.algorithm},
        claims=claims,
        key=settings.jwt.secret_key,
    )
    return encoded_jwt
