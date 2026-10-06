import asyncio
import json
import os
import sys
from pathlib import Path

from app.config import JWTSettings, Settings
from app.files.ownership import restore_tree_ownership_task
from app.files.utils import makedirs_with_ownership
from app.mcmap.cache import ServerMapCache
from app.runtime import Runtime


def owner(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_uid, stat.st_gid]


async def main() -> None:
    root = Path("/owned")
    data = root / "data"
    data.mkdir()
    os.chown(data, 12345, 23456)
    existing = data / "existing"
    existing.mkdir()
    os.chown(existing, 34567, 45678)
    (existing / "keep.bin").write_bytes(b"existing bytes\x00\xff")
    os.chown(existing / "keep.bin", 34567, 45678)
    sentinel = root / "outside.bin"
    sentinel.write_bytes(b"outside bytes\x00\xff")
    os.chown(sentinel, 33333, 44444)
    runtime = Runtime(Settings(  # type: ignore
        server_path=root / "servers", archive_path=root / "archives",
        logs_dir=root / "logs", database_url=f"sqlite+aiosqlite:///{root / 'db.sqlite3'}",
        master_token="ownership-test", jwt=JWTSettings(secret_key="ownership-test-" + "x" * 32),
        restic=None,
    ))
    try:
        with runtime.bind():
            await makedirs_with_ownership(existing / "new" / "deep", data)
            await makedirs_with_ownership(existing / "new" / "deep", data)
            cache = ServerMapCache(data)
            if sys.argv[1] == "existing":
                cache.cache_dir.mkdir()
                os.chown(cache.cache_dir, 34567, 45678)
            await cache.ensure_dir(cache.tiles_dir("world/region"))
            await cache.ensure_dir(cache.tiles_dir("world/region"))
            before = {
                "data": owner(data), "existing": owner(existing),
                "existing_file": owner(existing / "keep.bin"),
                "new": owner(existing / "new"), "deep": owner(existing / "new/deep"),
                "cache": owner(cache.cache_dir), "tiles": owner(cache.cache_dir / "tiles"),
                "world": owner(cache.cache_dir / "tiles/world"),
                "region": owner(cache.cache_dir / "tiles/world/region"),
            }
            (existing / "new/deep/created.bin").write_bytes(b"created bytes\x00\xff")
            os.chown(existing / "new/deep/created.bin", 55555, 55556)
            progress = [event async for event in restore_tree_ownership_task(data)]
            after = {
                path.relative_to(data).as_posix(): owner(path)
                for path in [data, existing, existing / "keep.bin", existing / "new",
                             existing / "new/deep", existing / "new/deep/created.bin",
                             cache.cache_dir, cache.cache_dir / "tiles",
                             cache.cache_dir / "tiles/world", cache.cache_dir / "tiles/world/region"]
            }
            print(json.dumps({
                "before": before, "after": after,
                "result": progress[-1].result, "progress": progress[-1].progress,
                "existing_bytes": (existing / "keep.bin").read_bytes().hex(),
                "created_bytes": (existing / "new/deep/created.bin").read_bytes().hex(),
                "outside_owner": owner(sentinel), "outside_bytes": sentinel.read_bytes().hex(),
            }), flush=True)
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
