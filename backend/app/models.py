from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import JSON, TEXT, DateTime, Integer, String
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


# Cron System Enums and Models


class CronJobStatus(str, Enum):
    """CronJob status enumeration for the cron management system."""

    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ExecutionStatus(str, Enum):
    """Execution status enumeration for cron job execution records."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CronJob(Base):
    """CronJob configuration table for the cron management system."""

    __tablename__ = "cronjob"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cronjob_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    identifier: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    cron: Mapped[str] = mapped_column(String(100))
    second: Mapped[Optional[str]] = mapped_column(String(20))
    params_json: Mapped[str] = mapped_column(TEXT)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[CronJobStatus] = mapped_column(
        SQLAlchemyEnum(CronJobStatus), default=CronJobStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CronJobExecution(Base):
    """CronJob execution record table for tracking cron job execution history."""

    __tablename__ = "cronjob_execution"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cronjob_id: Mapped[str] = mapped_column(String(255), index=True)
    execution_id: Mapped[str] = mapped_column(String(50), unique=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[ExecutionStatus] = mapped_column(SQLAlchemyEnum(ExecutionStatus))
    messages_json: Mapped[str] = mapped_column(TEXT, default="[]")
