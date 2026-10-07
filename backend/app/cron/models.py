from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import TEXT, Boolean, Integer, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDatetime


class CronJobStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CronJob(Base):
    __tablename__ = "cronjob"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cronjob_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    identifier: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    cron: Mapped[str] = mapped_column(String(100))
    second: Mapped[str | None] = mapped_column(String(20))
    params_json: Mapped[str] = mapped_column(TEXT)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[CronJobStatus] = mapped_column(
        SQLAlchemyEnum(CronJobStatus), default=CronJobStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )
    managed_purpose: Mapped[str | None] = mapped_column(String(40))


class CronJobExecution(Base):
    __tablename__ = "cronjob_execution"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cronjob_id: Mapped[str] = mapped_column(String(255), index=True)
    execution_id: Mapped[str] = mapped_column(String(50), unique=True)
    started_at: Mapped[datetime] = mapped_column(TZDatetime())
    ended_at: Mapped[datetime | None] = mapped_column(TZDatetime())
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ExecutionStatus] = mapped_column(SQLAlchemyEnum(ExecutionStatus))
    messages_json: Mapped[str] = mapped_column(TEXT, default="[]")
