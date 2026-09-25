from datetime import UTC, datetime

from sqlalchemy import TEXT, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDatetime


class ServerTemplate(Base):
    __tablename__ = "server_template"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    yaml_template: Mapped[str] = mapped_column(TEXT)
    variable_definitions_json: Mapped[str] = mapped_column(TEXT, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )


class DefaultVariableConfig(Base):
    """Single-row table holding default variables pre-filled when creating templates."""

    __tablename__ = "default_variable_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    variable_definitions_json: Mapped[str] = mapped_column(TEXT, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )
