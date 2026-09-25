from datetime import UTC, datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDatetime


class DynamicConfig(Base):
    __tablename__ = "dynamic_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    module_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    config_data: Mapped[dict] = mapped_column(JSON)
    config_schema_version: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        TZDatetime(), default=lambda: datetime.now(UTC)
    )
