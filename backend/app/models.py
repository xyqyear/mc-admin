from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import JSON, DateTime, String
from sqlalchemy import Enum as SQLAlchemyEnum
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# Pydantic models for request/response serialization
class UserBase(BaseModel):
    """Base Pydantic model for User."""

    username: str
    role: UserRole = UserRole.ADMIN


class UserPublic(UserBase):
    """Public User model for API responses."""

    id: int
    created_at: datetime


class UserCreate(BaseModel):
    """User creation model with validation."""

    username: str = PydanticField(min_length=3, max_length=50)
    password: str
    role: UserRole = UserRole.ADMIN


class DynamicConfig(Base):
    """Dynamic configuration table for modular configuration management."""

    __tablename__ = "dynamic_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    module_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    config_data: Mapped[dict] = mapped_column(JSON)
    config_schema_version: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
