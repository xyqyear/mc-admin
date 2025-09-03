from datetime import datetime, timedelta, timezone

from joserfc import jwt
from joserfc.jwk import OctKey
from passlib.context import CryptContext

from ..config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
key = OctKey.import_key(settings.jwt.secret_key)


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
            minutes=settings.jwt.access_token_expire_minutes
        )
    claims.update({"exp": expire})
    encoded_jwt = jwt.encode(
        header={"alg": settings.jwt.algorithm},
        claims=claims,
        key=key,
    )
    return encoded_jwt
