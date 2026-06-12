"""Unit tests for async_fs.resolve_inside containment checks."""

from pathlib import Path

import pytest

from app.utils import async_fs
from app.utils.async_fs import PathOutsideBaseError


async def test_path_inside_base(tmp_path):
    target = tmp_path / "data" / "world"
    target.mkdir(parents=True)
    resolved = await async_fs.resolve_inside(tmp_path, target)
    assert resolved == target.resolve()


async def test_base_itself_allowed(tmp_path):
    assert await async_fs.resolve_inside(tmp_path, tmp_path) == tmp_path.resolve()


async def test_nonexistent_path_inside_base(tmp_path):
    resolved = await async_fs.resolve_inside(tmp_path, tmp_path / "not-yet-created")
    assert resolved == (tmp_path / "not-yet-created").resolve()


async def test_dotdot_escape_rejected(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (tmp_path / "outside").mkdir()
    with pytest.raises(PathOutsideBaseError):
        await async_fs.resolve_inside(base, base / ".." / "outside")


async def test_sibling_prefix_rejected(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    evil = tmp_path / "base-evil"
    evil.mkdir()
    with pytest.raises(PathOutsideBaseError):
        await async_fs.resolve_inside(base, evil)


async def test_symlink_escape_rejected(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (base / "link").symlink_to(outside)
    with pytest.raises(PathOutsideBaseError):
        await async_fs.resolve_inside(base, base / "link")
    with pytest.raises(PathOutsideBaseError):
        await async_fs.resolve_inside(base, base / "link" / "deeper.txt")


async def test_symlink_inside_base_allowed(tmp_path):
    base = tmp_path / "base"
    real = base / "real"
    real.mkdir(parents=True)
    (base / "alias").symlink_to(real)
    resolved = await async_fs.resolve_inside(base, base / "alias")
    assert resolved == real.resolve()


async def test_base_through_symlink_normalized(tmp_path):
    """The base itself is resolved too, so a symlinked base works."""
    real_base = tmp_path / "real-base"
    (real_base / "child").mkdir(parents=True)
    link_base = tmp_path / "link-base"
    link_base.symlink_to(real_base)
    resolved = await async_fs.resolve_inside(link_base, link_base / "child")
    assert resolved == (real_base / "child").resolve()


def test_error_is_value_error():
    assert issubclass(PathOutsideBaseError, ValueError)
