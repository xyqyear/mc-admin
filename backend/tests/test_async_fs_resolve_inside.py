"""Filesystem read contracts and containment checks."""

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


async def test_batch_resolution_preserves_order_duplicates_and_missing_link_targets(
    tmp_path,
):
    root = tmp_path / "data"
    real = root / "real"
    real.mkdir(parents=True)
    (real / "value").write_text("untouched")
    (root / "alias").symlink_to(real, target_is_directory=True)
    (root / "dangling").symlink_to(root / "missing", target_is_directory=True)
    base = tmp_path / "data-link"
    base.symlink_to(root, target_is_directory=True)
    paths = [
        base / "alias" / "value",
        base / "new",
        base / "dangling" / "child",
        base / "alias" / "value",
    ]
    assert await async_fs.resolve_many(paths, base=base) == (
        real / "value",
        root / "new",
        root / "missing" / "child",
        real / "value",
    )
    assert (real / "value").read_text() == "untouched"
    assert (root / "dangling").is_symlink()
    assert not (root / "missing").exists()


@pytest.mark.parametrize(
    "escape", ["../outside/value", "shortcut/value", "../data-other/value"]
)
async def test_batch_resolution_checks_every_candidate_for_escape(tmp_path, escape):
    base = tmp_path / "data"
    base.mkdir()
    inside = base / "value"
    inside.write_text("inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "value").write_text("outside")
    (tmp_path / "data-other").mkdir()
    (base / "shortcut").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathOutsideBaseError):
        await async_fs.resolve_many([inside, base / "new", base / escape], base=base)
    assert inside.read_text() == "inside"
    assert (outside / "value").read_text() == "outside"


async def test_batch_existence_reads_keep_dangling_links_and_input_order(tmp_path):
    target = tmp_path / "value"
    target.write_text("value")
    missing = tmp_path / "missing"
    link = tmp_path / "dangling"
    link.symlink_to(missing)
    assert await async_fs.lexists_many([missing, link, target, missing, link]) == (
        False,
        True,
        True,
        False,
        True,
    )
    assert link.is_symlink()
    assert not missing.exists()
