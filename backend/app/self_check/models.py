from datetime import UTC, datetime

from sqlalchemy import TEXT, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDatetime


class SelfCheckRun(Base):
    __tablename__ = "self_check_run"
    __table_args__ = (
        Index("idx_self_check_run_scope_finished_id", "scope", "finished_at", "id"),
        Index(
            "idx_self_check_run_scope_check_finished_id",
            "scope",
            "check_id",
            "finished_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    trigger: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(20))
    check_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(TZDatetime())
    finished_at: Mapped[datetime] = mapped_column(TZDatetime(), index=True)
    summary_json: Mapped[str] = mapped_column(TEXT)
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)


class SelfCheckFinding(Base):
    __tablename__ = "self_check_finding"
    __table_args__ = (
        Index("idx_self_check_finding_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32))
    check_id: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    server_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(TEXT)
    evidence_json: Mapped[str] = mapped_column(TEXT)
    remediation_json: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )
