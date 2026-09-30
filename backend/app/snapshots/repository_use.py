from collections import Counter
from collections.abc import Generator, Sequence
from contextlib import contextmanager

from fastapi import HTTPException


class RepositoryUse:
    def __init__(self) -> None:
        self._readers = 0
        self._snapshots: Counter[str] = Counter()
        self._maintenance = False

    @property
    def active_snapshots(self) -> frozenset[str]:
        return frozenset(self._snapshots)

    @contextmanager
    def retain(self, snapshot_ids: Sequence[str] = ()) -> Generator[None]:
        ids = set(snapshot_ids)
        if self._maintenance:
            raise HTTPException(status_code=423, detail="快照仓库正在维护，请稍后重试")
        if self._readers >= 256 or len(self._snapshots.keys() | ids) > 256:
            raise HTTPException(
                status_code=423, detail="活动快照引用过多，请等待已有操作结束"
            )
        self._readers += 1
        self._snapshots.update(ids)
        try:
            yield
        finally:
            self._readers -= 1
            self._snapshots.subtract(ids)
            self._snapshots += Counter()

    @contextmanager
    def maintain(self) -> Generator[None]:
        if self._maintenance or self._readers:
            raise HTTPException(
                status_code=423, detail="快照仓库仍被活动操作使用，无法删除快照或清理锁"
            )
        self._maintenance = True
        try:
            yield
        finally:
            self._maintenance = False
