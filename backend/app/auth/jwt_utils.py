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


def get_token_expiry(expires_delta: timedelta | None = None) -> datetime:
    """Calculate JWT token expiration time"""
    if expires_delta:
        return datetime.now(timezone.utc) + expires_delta
    else:
        return datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt.access_token_expire_minutes
        )


def create_access_token(jwt_claims):
    # Convert JwtClaims to dict (already includes exp)
    claims = jwt_claims.model_dump()
    # Convert datetime to timestamp for JWT
    if isinstance(claims.get("exp"), datetime):
        claims["exp"] = claims["exp"].timestamp()
    encoded_jwt = jwt.encode(
        header={"alg": settings.jwt.algorithm},
        claims=claims,
        key=key,
    )
    return encoded_jwt
