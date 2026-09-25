from datetime import datetime

from sqlalchemy import TEXT, Boolean, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDatetime


class OperationJournalEntry(Base):
    __tablename__ = "operation_journal"
    __table_args__ = (
        Index("ix_operation_journal_state_updated", "state", "updated_at"),
        Index("ix_operation_journal_retention", "writers_stopped", "has_recovery_refs", "ended_at"),
        UniqueConstraint("origin", "legacy_id", name="uq_operation_journal_legacy"),
    )

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    legacy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    running_intent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    configuration_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resources_json: Mapped[str] = mapped_column(TEXT)
    state: Mapped[str] = mapped_column(String(16))
    phase: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TZDatetime())
    updated_at: Mapped[datetime] = mapped_column(TZDatetime())
    ended_at: Mapped[datetime | None] = mapped_column(TZDatetime(), nullable=True)
    data_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    writers_stopped: Mapped[bool] = mapped_column(Boolean, default=True)
    ownership_known: Mapped[bool] = mapped_column(Boolean, default=True)
    processes_json: Mapped[str] = mapped_column(TEXT, default="[]")
    recovery_refs_json: Mapped[str] = mapped_column(TEXT, default="[]")
    has_recovery_refs: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cache_degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(TZDatetime(), nullable=True)
