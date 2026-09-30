from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import TEXT, Boolean, Integer, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDatetime


class RestorationType(str, Enum):
    GLOBAL = "global"
    SERVER = "server"
    PATHS = "paths"
    WORLD = "world"
    DIMENSION = "dimension"
    REGIONS = "regions"
    CHUNKS = "chunks"


class RestorationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class Restoration(Base):
    __tablename__ = "restoration"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    server_id: Mapped[str | None] = mapped_column(
        String(100), index=True, nullable=True
    )
    type: Mapped[RestorationType] = mapped_column(SQLAlchemyEnum(RestorationType))
    server_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    binding_issue: Mapped[str | None] = mapped_column(String(80), nullable=True)
    scope_json: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    targets_json: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    protection_json: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    operation_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, unique=True, index=True
    )
    rollback_of_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    entry_point: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_snapshot_id: Mapped[str] = mapped_column(String(64))
    safety_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selection_json: Mapped[str] = mapped_column(TEXT)
    is_rollback: Mapped[bool] = mapped_column(Boolean, default=False)
    initiated_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(TZDatetime(), nullable=True)
    status: Mapped[RestorationStatus] = mapped_column(
        SQLAlchemyEnum(RestorationStatus), default=RestorationStatus.RUNNING
    )
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)
