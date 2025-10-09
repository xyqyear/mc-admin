from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import JSON, TEXT, DateTime, Index, Integer, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class TZDatetime(TypeDecorator):
    """Custom DateTime type that ensures timezone-aware datetimes."""

    impl = DateTime(timezone=True)

    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            raise ValueError(
                "Naive datetime is not allowed. Please provide a timezone-aware datetime."
            )
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            # Assume UTC if no timezone info is present
            return value.replace(tzinfo=timezone.utc)
        return value


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
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
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
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
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
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


class CronJobExecution(Base):
    """CronJob execution record table for tracking cron job execution history."""

    __tablename__ = "cronjob_execution"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cronjob_id: Mapped[str] = mapped_column(String(255), index=True)
    execution_id: Mapped[str] = mapped_column(String(50), unique=True)
    started_at: Mapped[datetime] = mapped_column(TZDatetime())
    ended_at: Mapped[Optional[datetime]] = mapped_column(TZDatetime())
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[ExecutionStatus] = mapped_column(SQLAlchemyEnum(ExecutionStatus))
    messages_json: Mapped[str] = mapped_column(TEXT, default="[]")


# Server Tracking System Models


class ServerStatus(str, Enum):
    """Server status enumeration."""

    ACTIVE = "active"
    REMOVED = "removed"


class Server(Base):
    """Server instance tracking table."""

    __tablename__ = "server"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[ServerStatus] = mapped_column(
        SQLAlchemyEnum(ServerStatus), default=ServerStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


class SystemHeartbeat(Base):
    """System heartbeat table for crash detection.

    This table only contains one record that is updated on each heartbeat.
    """

    __tablename__ = "system_heartbeat"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    timestamp: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


# Player Management System Models


class Player(Base):
    """Player table for tracking all players."""

    __tablename__ = "player"

    player_db_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    current_name: Mapped[str] = mapped_column(String(16))
    skin_data: Mapped[Optional[bytes]] = mapped_column()
    avatar_data: Mapped[Optional[bytes]] = mapped_column()
    last_seen: Mapped[Optional[datetime]] = mapped_column(TZDatetime())
    last_skin_update: Mapped[Optional[datetime]] = mapped_column(TZDatetime())
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


class PlayerSession(Base):
    """Player gaming session records."""

    __tablename__ = "player_session"
    __table_args__ = (
        # Composite indexes for efficient time-based queries
        Index("idx_player_session_player_time", "player_db_id", "joined_at"),
        Index("idx_player_session_server_time", "server_db_id", "joined_at"),
        # Indexes for efficient online player queries
        Index("idx_player_session_server_online", "server_db_id", "left_at"),
        Index(
            "idx_player_session_player_server_online",
            "player_db_id",
            "server_db_id",
            "left_at",
        ),
    )

    session_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_db_id: Mapped[int] = mapped_column(Integer, index=True)
    server_db_id: Mapped[int] = mapped_column(Integer, index=True)
    joined_at: Mapped[datetime] = mapped_column(TZDatetime())
    left_at: Mapped[Optional[datetime]] = mapped_column(TZDatetime())
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)


class PlayerChatMessage(Base):
    """Player chat messages."""

    __tablename__ = "player_chat_message"
    __table_args__ = (
        # Composite indexes for efficient time-based queries
        Index("idx_player_chat_player_time", "player_db_id", "sent_at"),
        Index("idx_player_chat_server_time", "server_db_id", "sent_at"),
    )

    message_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_db_id: Mapped[int] = mapped_column(Integer, index=True)
    server_db_id: Mapped[int] = mapped_column(Integer, index=True)
    message_text: Mapped[str] = mapped_column(TEXT)
    sent_at: Mapped[datetime] = mapped_column(TZDatetime())


class PlayerAchievement(Base):
    """Player achievements."""

    __tablename__ = "player_achievement"
    __table_args__ = (
        Index(
            "idx_player_achievement_unique",
            "player_db_id",
            "server_db_id",
            "achievement_name",
            unique=True,
        ),
        # Time-based indexes for recent achievements queries
        Index("idx_player_achievement_time", "earned_at"),
        Index("idx_player_achievement_player_time", "player_db_id", "earned_at"),
        Index("idx_player_achievement_server_time", "server_db_id", "earned_at"),
    )

    achievement_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_db_id: Mapped[int] = mapped_column(Integer, index=True)
    server_db_id: Mapped[int] = mapped_column(Integer, index=True)
    achievement_name: Mapped[str] = mapped_column(String(255))
    earned_at: Mapped[datetime] = mapped_column(TZDatetime())


