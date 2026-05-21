from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Optional

from app.world import region_manifest


def test_region_manifest_worker_count_comes_from_config(tmp_path: Path, monkeypatch):
    region_dir = tmp_path / "region"
    region_dir.mkdir()
    for x in range(3):
        (region_dir / f"r.{x}.0.mca").write_bytes(b"mca")

    seen_workers: list[int] = []

    class FakePool:
        def __init__(self, max_workers: int) -> None:
            seen_workers.append(max_workers)

        def __enter__(self) -> "FakePool":
            return self

        def __exit__(
            self,
            exc_type: Optional[type[BaseException]],
            exc: Optional[BaseException],
            tb: Any,
        ) -> bool:
            return False

        def map(
            self,
            fn: Callable[[tuple[str, int, int]], tuple[int, int, int] | None],
            candidates: Iterable[tuple[str, int, int]],
        ) -> Iterable[tuple[int, int, int] | None]:
            return map(fn, candidates)

    monkeypatch.setattr(
        region_manifest,
        "config",
        SimpleNamespace(world=SimpleNamespace(region_stat_workers=2)),
    )
    monkeypatch.setattr(region_manifest, "ThreadPoolExecutor", FakePool)

    rows = region_manifest.list_region_manifest_sync(region_dir)

    assert seen_workers == [2]
    assert [(x, z) for x, z, _ in rows] == [(0, 0), (1, 0), (2, 0)]
