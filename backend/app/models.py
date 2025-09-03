from enum import Enum
from typing import Optional

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models with async support."""

    pass


class UserRole(str, Enum):
    ADMIN = "admin"
    OWNER = "owner"


class User(Base):
    """User table ORM model."""

    __tablename__ = "user"

    id: Mapped[Optional[int]] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        SQLAlchemyEnum(UserRole), default=UserRole.ADMIN
    )


# Pydantic models for request/response serialization
class UserBase(BaseModel):
    """Base Pydantic model for User."""

    username: str
    role: UserRole = UserRole.ADMIN


class UserPublic(UserBase):
    """Public User model for API responses."""

    id: int


class UserCreate(BaseModel):
    """User creation model with validation."""

    username: str = PydanticField(min_length=3, max_length=50)
    password: str
