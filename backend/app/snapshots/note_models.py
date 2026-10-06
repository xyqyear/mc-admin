from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class SnapshotNote(Base):
    __tablename__ = "snapshot_notes"
    __table_args__ = (CheckConstraint("length(note) <= 500", name="snapshot_note_length"),)

    repository_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
