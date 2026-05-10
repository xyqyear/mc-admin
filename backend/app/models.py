from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import JSON, TEXT, Boolean, DateTime, Index, Integer, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class TZDatetime(TypeDecorator):
    """DateTime that rejects naive values on bind and assumes UTC on read."""

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
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(AsyncAttrs, DeclarativeBase):
    pass


class UserRole(str, Enum):
    ADMIN = "admin"
    OWNER = "owner"


class User(Base):
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


class UserBase(BaseModel):
    username: str
    role: UserRole = UserRole.ADMIN


class UserPublic(UserBase):
    id: int
    created_at: datetime


class UserCreate(BaseModel):
    username: str = PydanticField(min_length=3, max_length=50)
    password: str
    role: UserRole = UserRole.ADMIN


class DynamicConfig(Base):
    __tablename__ = "dynamic_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    module_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    config_data: Mapped[dict] = mapped_column(JSON)
    config_schema_version: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


class CronJobStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CronJob(Base):
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
    __tablename__ = "cronjob_execution"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cronjob_id: Mapped[str] = mapped_column(String(255), index=True)
    execution_id: Mapped[str] = mapped_column(String(50), unique=True)
    started_at: Mapped[datetime] = mapped_column(TZDatetime())
    ended_at: Mapped[Optional[datetime]] = mapped_column(TZDatetime())
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[ExecutionStatus] = mapped_column(SQLAlchemyEnum(ExecutionStatus))
    messages_json: Mapped[str] = mapped_column(TEXT, default="[]")


class ServerStatus(str, Enum):
    ACTIVE = "active"
    REMOVED = "removed"


class Server(Base):
    __tablename__ = "server"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[ServerStatus] = mapped_column(
        SQLAlchemyEnum(ServerStatus), default=ServerStatus.ACTIVE
    )
    template_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    template_snapshot_json: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    variable_values_json: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


class ServerTemplate(Base):
    __tablename__ = "server_template"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    yaml_template: Mapped[str] = mapped_column(TEXT)
    variable_definitions_json: Mapped[str] = mapped_column(TEXT, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


class SystemHeartbeat(Base):
    """Single-row table whose timestamp is bumped on each heartbeat for crash detection."""

    __tablename__ = "system_heartbeat"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    timestamp: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


class Player(Base):
    __tablename__ = "player"

    player_db_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    current_name: Mapped[str] = mapped_column(String(16))
    skin_data: Mapped[Optional[bytes]] = mapped_column()
    avatar_data: Mapped[Optional[bytes]] = mapped_column()
    last_skin_update: Mapped[Optional[datetime]] = mapped_column(TZDatetime())
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


class PlayerSession(Base):
    __tablename__ = "player_session"
    __table_args__ = (
        Index("idx_player_session_player_time", "player_db_id", "joined_at"),
        Index("idx_player_session_server_time", "server_db_id", "joined_at"),
        Index("idx_player_session_server_online", "server_db_id", "left_at"),
        Index(
            "idx_player_session_player_server_online",
            "player_db_id",
            "server_db_id",
            "left_at",
        ),
        Index("idx_player_session_player_left_at", "player_db_id", "left_at"),
    )

    session_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_db_id: Mapped[int] = mapped_column(Integer, index=True)
    server_db_id: Mapped[int] = mapped_column(Integer, index=True)
    joined_at: Mapped[datetime] = mapped_column(TZDatetime())
    left_at: Mapped[Optional[datetime]] = mapped_column(TZDatetime())
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)


class PlayerChatMessage(Base):
    __tablename__ = "player_chat_message"
    __table_args__ = (
        Index("idx_player_chat_player_time", "player_db_id", "sent_at"),
        Index("idx_player_chat_server_time", "server_db_id", "sent_at"),
    )

    message_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_db_id: Mapped[int] = mapped_column(Integer, index=True)
    server_db_id: Mapped[int] = mapped_column(Integer, index=True)
    message_text: Mapped[str] = mapped_column(TEXT)
    sent_at: Mapped[datetime] = mapped_column(TZDatetime())


class PlayerAchievement(Base):
    __tablename__ = "player_achievement"
    __table_args__ = (
        Index(
            "idx_player_achievement_unique",
            "player_db_id",
            "server_db_id",
            "achievement_name",
            unique=True,
        ),
        Index("idx_player_achievement_time", "earned_at"),
        Index("idx_player_achievement_player_time", "player_db_id", "earned_at"),
        Index("idx_player_achievement_server_time", "server_db_id", "earned_at"),
    )

    achievement_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_db_id: Mapped[int] = mapped_column(Integer, index=True)
    server_db_id: Mapped[int] = mapped_column(Integer, index=True)
    achievement_name: Mapped[str] = mapped_column(String(255))
    earned_at: Mapped[datetime] = mapped_column(TZDatetime())


class DefaultVariableConfig(Base):
    """Single-row table holding default variables pre-filled when creating templates."""

    __tablename__ = "default_variable_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    variable_definitions_json: Mapped[str] = mapped_column(TEXT, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )


class RestorationType(str, Enum):
    """Granularity of a world-restoration operation."""

    WORLD = "world"
    DIMENSION = "dimension"
    REGIONS = "regions"
    CHUNKS = "chunks"


class RestorationStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class Restoration(Base):
    """Restoration history. Rollbacks are flat rows distinguished by ``is_rollback``."""

    __tablename__ = "restoration"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    server_id: Mapped[str] = mapped_column(String(100), index=True)
    type: Mapped[RestorationType] = mapped_column(SQLAlchemyEnum(RestorationType))
    source_snapshot_id: Mapped[str] = mapped_column(String(64))
    safety_snapshot_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    selection_json: Mapped[str] = mapped_column(TEXT)
    is_rollback: Mapped[bool] = mapped_column(Boolean, default=False)
    initiated_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(TZDatetime(), nullable=True)
    status: Mapped[RestorationStatus] = mapped_column(
        SQLAlchemyEnum(RestorationStatus), default=RestorationStatus.RUNNING
    )
    error_message: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)


class RestorationSelection(BaseModel):
    """What is being snapshotted/restored. ``chunks`` holds absolute chunk coords."""

    type: RestorationType
    # Required for DIMENSION/REGIONS/CHUNKS; ignored for WORLD. Path relative
    # to the server's data/ dir (e.g. "world/region"); the world root dir name
    # is its prefix, so it uniquely identifies a dimension across roots.
    region_dir_relpath: Optional[str] = None
    regions: list[Tuple[int, int]] = PydanticField(default_factory=list)
    chunks: list[Tuple[int, int]] = PydanticField(default_factory=list)
