import posixpath
from collections.abc import Sequence
from pathlib import Path

from fastapi import HTTPException

from ..utils import async_fs


async def resolve_file_path(base_path: Path, path: str) -> Path:
    candidate = base_path / path.lstrip("/")
    try:
        await async_fs.resolve_inside(base_path, candidate)
    except async_fs.PathOutsideBaseError:
        raise HTTPException(status_code=400, detail="Path escapes file directory")
    # Rename and unlink must act on a symlink itself, not its resolved target.
    return candidate


def validate_file_name(name: str) -> None:
    if not name or name in {".", ".."} or "/" in name:
        raise HTTPException(status_code=400, detail="Invalid file name")


async def normalize_selected_paths(base_path: Path, paths: Sequence[str]) -> tuple[str, ...]:
    if not paths:
        raise HTTPException(status_code=400, detail="请选择文件或文件夹")
    normalized: set[str] = set()
    for path in paths:
        await resolve_file_path(base_path, path)
        relative = posixpath.normpath(path.lstrip("/"))
        normalized.add("" if relative == "." else relative)
    roots: list[str] = []
    for relative in sorted(normalized, key=lambda path: (len(Path(path).parts), path)):
        if not any(not parent or relative.startswith(parent + "/") for parent in roots):
            roots.append(relative)
    return tuple(sorted(roots))
