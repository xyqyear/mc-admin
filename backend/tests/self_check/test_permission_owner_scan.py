from os import stat_result
from pathlib import Path

import pytest

from app.config import settings
from app.self_check.checks.files import scan_permission_owner_with_fd


def path_with_uid(path: Path, uid: int) -> Path:
    class PathWithUid(type(path)):
        def stat(self, *args, **kwargs) -> stat_result:
            original = super().stat(*args, **kwargs)
            values = list(original)
            values[4] = uid
            return stat_result(values)

    return PathWithUid(path)


async def test_owner_scan_ignores_mode_changes(tmp_path: Path) -> None:
    root = tmp_path / "server"
    root.mkdir()
    file_path = root / "server.properties"
    file_path.write_text("motd=test\n")
    file_path.chmod(0o600)

    scan = await scan_permission_owner_with_fd(root, 100)

    assert scan.mismatched == 0
    assert scan.samples == []
    assert scan.truncated is False
    assert scan.errors == []


async def test_owner_scan_reports_uid_mismatches(tmp_path: Path) -> None:
    root = tmp_path / "server"
    root.mkdir()
    mismatched = root / "uid-mismatch.dat"
    mismatched.write_bytes(b"")
    root_with_different_uid = path_with_uid(root, root.stat().st_uid + 1)

    scan = await scan_permission_owner_with_fd(root_with_different_uid, 100)

    assert scan.root_uid == root.stat().st_uid + 1
    assert scan.mismatched == 1
    assert scan.truncated is False
    assert scan.errors == []
    assert scan.samples == [{"path": str(mismatched), "uid": root.stat().st_uid}]


async def test_owner_scan_truncates_uid_mismatches(tmp_path: Path) -> None:
    root = tmp_path / "server"
    root.mkdir()
    for index in range(3):
        path = root / f"mismatch-{index}.txt"
        path.write_text(str(index))
    root_with_different_uid = path_with_uid(root, root.stat().st_uid + 1)

    scan = await scan_permission_owner_with_fd(root_with_different_uid, 2)

    assert scan.mismatched == 2
    assert len(scan.samples) == 2
    assert scan.truncated is True
    assert scan.errors == []


async def test_owner_scan_reports_missing_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "server"
    root.mkdir()
    monkeypatch.setattr(settings, "fd_binary_path", Path("/missing/fd"))

    scan = await scan_permission_owner_with_fd(root, 100)

    assert scan.mismatched == 0
    assert scan.truncated is False
    assert scan.samples == []
    assert scan.errors == ["fd command not found at /missing/fd"]
