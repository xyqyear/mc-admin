from datetime import UTC

from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
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
            return value.replace(tzinfo=UTC)
        return value


class Base(AsyncAttrs, DeclarativeBase):
    pass
