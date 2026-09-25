from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import TEXT, Boolean, CheckConstraint, Index, Integer, String
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
    __table_args__ = (
        Index("uq_cronjob_managed_binding", "managed_server_generation", "managed_purpose", unique=True),
        CheckConstraint(
            "(managed_purpose IS NULL AND managed_server_generation IS NULL AND managed_binding_issue IS NULL) OR "
            "(managed_purpose IS NOT NULL AND ((managed_server_generation IS NOT NULL AND managed_binding_issue IS NULL) OR "
            "(managed_server_generation IS NULL AND managed_binding_issue IS NOT NULL)))",
            name="ck_cronjob_managed_binding",
        ),
    )

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
    managed_server_generation: Mapped[int | None] = mapped_column(Integer)
    managed_purpose: Mapped[str | None] = mapped_column(String(40))
    managed_binding_issue: Mapped[str | None] = mapped_column(String(80))


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
