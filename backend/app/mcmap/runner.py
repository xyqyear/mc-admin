import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, List, Optional, TypeVar

import aiofiles.os as aioos
from pydantic import TypeAdapter, ValidationError

from ..config import settings
from ..logger import logger
from .events import (
    MCMAP_GENERIC_EVENT_ADAPTER,
    MCMapGenericEvent,
    MCMapProtocolError,
)

TERMINATE_GRACE_SECONDS = 2.0
MCMAP_STREAM_LIMIT_BYTES = 16 * 1024 * 1024
EventT = TypeVar("EventT")


class MCMapProcess:
    def __init__(self, proc: asyncio.subprocess.Process):
        self._proc = proc
        self._terminated = False

    def __aiter__(self) -> AsyncIterator[MCMapGenericEvent]:
        return self.events(MCMAP_GENERIC_EVENT_ADAPTER)

    def events(self, adapter: TypeAdapter[EventT]) -> AsyncIterator[EventT]:
        return self._read_events(adapter)

    async def _read_events(
        self, adapter: TypeAdapter[EventT]
    ) -> AsyncIterator[EventT]:
        assert self._proc.stdout is not None
        async for raw in self._proc.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                yield adapter.validate_json(line)
            except ValidationError as e:
                logger.warning("mcmap: invalid JSON event: %r (%s)", line, e)
                raise MCMapProtocolError("mcmap emitted an invalid JSON event") from e

    async def terminate(self) -> None:
        if self._terminated or self._proc.returncode is not None:
            return
        self._terminated = True
        try:
            self._proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=TERMINATE_GRACE_SECONDS)
        except asyncio.TimeoutError:
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
            await self._proc.wait()

    async def stderr(self) -> str:
        if self._proc.stderr is None:
            return ""
        data = await self._proc.stderr.read()
        return data.decode(errors="replace")

    @property
    def returncode(self) -> Optional[int]:
        return self._proc.returncode


async def _chown_args_for(owned_by: Path) -> List[str]:
    if os.geteuid() != 0:
        return []
    try:
        st = await aioos.stat(owned_by)
    except FileNotFoundError:
        logger.warning(
            "mcmap: owned_by path %s does not exist; skipping --chown", owned_by
        )
        return []
    return ["--chown", f"{st.st_uid}:{st.st_gid}"]


async def _spawn(args: List[str], owned_by: Path) -> asyncio.subprocess.Process:
    full_args: List[str] = ["--json", *args, *await _chown_args_for(owned_by)]
    return await asyncio.create_subprocess_exec(
        str(settings.mcmap_binary_path),
        *full_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=MCMAP_STREAM_LIMIT_BYTES,
    )


@asynccontextmanager
async def _run(args: List[str], owned_by: Path) -> AsyncIterator[MCMapProcess]:
    proc = await _spawn(args, owned_by=owned_by)
    wrapper = MCMapProcess(proc)
    try:
        yield wrapper
    finally:
        await wrapper.terminate()


@asynccontextmanager
async def download_client(
    version: str, target: Path, *, owned_by: Path
) -> AsyncIterator[MCMapProcess]:
    async with _run(["download-client", version, str(target)], owned_by) as p:
        yield p


@asynccontextmanager
async def gen_palette(
    packs: List[Path],
    output: Path,
    *,
    level_dat: Optional[Path],
    owned_by: Path,
) -> AsyncIterator[MCMapProcess]:
    args: List[str] = ["gen-palette", "-o", str(output)]
    if level_dat is not None:
        args.extend(["--level-dat", str(level_dat)])
    for pack in packs:
        args.extend(["-p", str(pack)])
    async with _run(args, owned_by) as p:
        yield p


@asynccontextmanager
async def render(
    palette: Path,
    output_dir: Path,
    mcas: List[Path],
    threads: int,
    *,
    owned_by: Path,
) -> AsyncIterator[MCMapProcess]:
    args: List[str] = [
        "render",
        "-p",
        str(palette),
        "-o",
        str(output_dir),
        "--split",
        "--preserve-mtime",
        "-j",
        str(threads),
    ]
    for mca in mcas:
        args.extend(["-r", str(mca)])
    async with _run(args, owned_by) as p:
        yield p


def _serialize_chunks(chunks: List[tuple[int, int]]) -> str:
    return ";".join(f"{x},{z}" for x, z in chunks)


@asynccontextmanager
async def replace_chunks(
    *,
    source_mca: Path,
    target_mca: Path,
    chunks: List[tuple[int, int]],
    owned_by: Path,
) -> AsyncIterator[MCMapProcess]:
    if not chunks:
        raise ValueError("replace_chunks requires at least one chunk coord")
    args: List[str] = [
        "replace-chunks",
        "-s",
        str(source_mca),
        "-t",
        str(target_mca),
        "-c",
        _serialize_chunks(chunks),
    ]
    async with _run(args, owned_by) as p:
        yield p


@asynccontextmanager
async def remove_chunks(
    *,
    target_mca: Path,
    chunks: List[tuple[int, int]],
    owned_by: Path,
) -> AsyncIterator[MCMapProcess]:
    if not chunks:
        raise ValueError("remove_chunks requires at least one chunk coord")
    args: List[str] = [
        "remove-chunks",
        "-t",
        str(target_mca),
        "-c",
        _serialize_chunks(chunks),
    ]
    async with _run(args, owned_by) as p:
        yield p


def parse_event_for_test(line: bytes) -> Any:
    return MCMAP_GENERIC_EVENT_ADAPTER.validate_json(line.strip())
