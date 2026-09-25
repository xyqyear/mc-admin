from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import TEXT, Index, Integer, String, text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDatetime


class ServerStatus(str, Enum):
    ACTIVE = "active"
    REMOVED = "removed"


class Server(Base):
    __tablename__ = "server"
    __table_args__ = (
        Index(
            "uq_server_active_name", "server_id", unique=True,
            sqlite_where=text("status='ACTIVE'"),
            postgresql_where=text("status='ACTIVE'"),
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[ServerStatus] = mapped_column(
        SQLAlchemyEnum(ServerStatus), default=ServerStatus.ACTIVE
    )
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_snapshot_json: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    variable_values_json: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )
