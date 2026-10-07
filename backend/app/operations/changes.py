import base64
import binascii
import json
from collections import deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import uuid4

from .journal_types import TERMINAL_STATES, OperationRecord, ResourceReference


@dataclass(frozen=True)
class OperationChange:
    sequence: int
    operation_id: str
    kind: str
    state: str
    data_changed: bool
    updated_at: datetime
    ended_at: datetime | None
    resources: tuple[ResourceReference, ...]


@dataclass(frozen=True)
class OperationChanges:
    items: tuple[OperationChange, ...]
    next_cursor: str
    has_more: bool
    active_count: int
    reset_required: bool


class OperationChangeFeed:
    def __init__(self, *, max_records: int = 2000, max_bytes: int = 4 * 1024 * 1024) -> None:
        if min(max_records, max_bytes) < 1:
            raise ValueError("Operation notification capacities must be positive")
        self.max_records = max_records
        self.max_bytes = max_bytes
        self._epoch = uuid4().hex
        self._sequence = 0
        self._discarded_through = 0
        self._bytes = 0
        self._items: deque[tuple[OperationChange, int]] = deque()
        self._active: set[str] = set()

    def initialize_active(self, operation_ids: Iterable[str]) -> None:
        self._active = set(operation_ids)

    def reset(self) -> None:
        self._epoch = uuid4().hex
        self._sequence = self._discarded_through = self._bytes = 0
        self._items.clear()

    def close(self) -> None:
        self.reset()
        self._active.clear()

    def track_state(self, record: OperationRecord) -> None:
        if record.state in TERMINAL_STATES:
            self._active.discard(record.operation_id)
        else:
            self._active.add(record.operation_id)

    def publish(self, record: OperationRecord) -> None:
        self.track_state(record)
        self._sequence += 1
        item = OperationChange(
            sequence=self._sequence, operation_id=record.operation_id, kind=record.kind,
            state=record.state.value, data_changed=record.data_changed,
            updated_at=record.updated_at, ended_at=record.ended_at, resources=record.resources,
        )
        size = len(json.dumps(asdict(item), ensure_ascii=False, separators=(",", ":"), default=str).encode())
        if size > self.max_bytes:
            self._items.clear()
            self._bytes = 0
            self._discarded_through = self._sequence
            return
        self._items.append((item, size))
        self._bytes += size
        while len(self._items) > self.max_records or self._bytes > self.max_bytes:
            discarded, removed_bytes = self._items.popleft()
            self._discarded_through = discarded.sequence
            self._bytes -= removed_bytes

    def _cursor(self, sequence: int, head: int | None = None) -> str:
        value = f"{self._epoch}:{sequence}:{head if head is not None else ''}".encode()
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    def _position(self, cursor: str | None) -> tuple[int, int] | None:
        if cursor is None or len(cursor) > 160:
            return None
        try:
            value = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            epoch, sequence_text, head_text = value.decode("ascii").split(":")
            if not sequence_text.isdecimal() or (head_text and not head_text.isdecimal()):
                return None
            sequence, head = int(sequence_text), int(head_text) if head_text else self._sequence
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return None
        if epoch != self._epoch or not self._discarded_through <= sequence <= head <= self._sequence:
            return None
        return sequence, head

    def read(self, cursor: str | None = None, *, limit: int = 200) -> OperationChanges:
        if not 1 <= limit <= 1000:
            raise ValueError("Operation notification pagination is bounded")
        position = self._position(cursor)
        if position is None:
            return OperationChanges((), self._cursor(self._sequence), False, len(self._active), True)
        sequence, head = position
        items: list[OperationChange] = []
        for item, _ in self._items:
            if sequence < item.sequence <= head:
                items.append(item)
                if len(items) == limit:
                    break
        next_sequence = items[-1].sequence if items else sequence
        has_more = next_sequence < head
        return OperationChanges(
            tuple(items), self._cursor(next_sequence, head if has_more else None),
            has_more, len(self._active), False,
        )
