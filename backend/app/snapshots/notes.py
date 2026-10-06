from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from .note_models import SnapshotNote
from .restoration_store import SessionFactory


class SnapshotNotes:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def read(self, repository_id: str, snapshot_ids: Sequence[str]) -> dict[str, str]:
        notes: dict[str, str] = {}
        async with self._sessions() as session:
            for offset in range(0, len(snapshot_ids), 500):
                rows = await session.execute(
                    select(SnapshotNote.snapshot_id, SnapshotNote.note).where(
                        SnapshotNote.repository_id == repository_id,
                        SnapshotNote.snapshot_id.in_(snapshot_ids[offset:offset + 500]),
                    )
                )
                notes.update((snapshot_id, note) for snapshot_id, note in rows)
        return notes

    async def save(self, repository_id: str, snapshot_id: str, note: str) -> None:
        if len(note) > 500:
            raise ValueError("快照备注不能超过 500 字")
        statement = insert(SnapshotNote).values(
            repository_id=repository_id, snapshot_id=snapshot_id, note=note
        )
        statement = statement.on_conflict_do_update(
            index_elements=[SnapshotNote.repository_id, SnapshotNote.snapshot_id],
            set_={"note": statement.excluded.note},
        )
        async with self._sessions() as session:
            await session.execute(statement)
            await session.commit()
