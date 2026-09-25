import asyncio
import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, TypeVar

import aiofiles.os as aioos
from pydantic import TypeAdapter, ValidationError

from ..config import get_settings
from ..errors import log_safe_error
from ..logger import get_logger
from ..operations.context import bind_execution, current_execution
from ..operations.finalization import finalize
from ..operations.processes import spawn_process, stop_process
from .events import (
    MCMAP_GENERIC_EVENT_ADAPTER,
    MCMapGenericEvent,
    MCMapProtocolError,
)

TERMINATE_GRACE_SECONDS = 2.0
MCMAP_STREAM_LIMIT_BYTES = 16 * 1024 * 1024
MCMAP_STDERR_LIMIT_BYTES = 256 * 1024
EventT = TypeVar("EventT")


class MCMapProcess:
    def __init__(self, proc: asyncio.subprocess.Process):
        self._proc = proc
        self._terminated = False
        self._execution = current_execution()
        self._termination_task: asyncio.Task[None] | None = None
        self._stderr_tail = bytearray()
        self._stderr_task = (
            asyncio.create_task(self._drain_stderr(), name="mcmap-stderr")
            if proc.stderr is not None else None
        )

    async def _drain_stderr(self) -> None:
        assert self._proc.stderr is not None
        while chunk := await self._proc.stderr.read(65536):
            self._stderr_tail.extend(chunk)
            if len(self._stderr_tail) > MCMAP_STDERR_LIMIT_BYTES:
                del self._stderr_tail[:-MCMAP_STDERR_LIMIT_BYTES]

    def __aiter__(self) -> AsyncIterator[MCMapGenericEvent]:
        return self.events(MCMAP_GENERIC_EVENT_ADAPTER)

    def events(self, adapter: TypeAdapter[EventT]) -> AsyncGenerator[EventT]:
        return self._read_events(adapter)

    async def _read_events(
        self, adapter: TypeAdapter[EventT]
    ) -> AsyncGenerator[EventT]:
        assert self._proc.stdout is not None
        async for raw in self._proc.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                yield adapter.validate_json(line)
            except ValidationError as e:
                log_safe_error(e, "mcmap: invalid JSON event")
                raise MCMapProtocolError("mcmap emitted an invalid JSON event") from e
        await self._proc.wait()
        if self._stderr_task is not None:
            await asyncio.shield(self._stderr_task)

    async def terminate(self) -> None:
        if self._terminated:
            return
        if self._termination_task is None:
            with bind_execution(self._execution):
                self._termination_task = asyncio.create_task(self._terminate(), name="mcmap-terminate")
        await finalize(self._termination_task)

    async def _terminate(self) -> None:
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            await asyncio.gather(self._stderr_task, return_exceptions=True)
        await stop_process(self._proc, grace=TERMINATE_GRACE_SECONDS)
        self._terminated = True

    async def stderr(self) -> str:
        if self._stderr_task is not None and not self._stderr_task.cancelled():
            await asyncio.shield(self._stderr_task)
        return self._stderr_tail.decode(errors="replace")

    @property
    def returncode(self) -> int | None:
        return self._proc.returncode


async def _chown_args_for(owned_by: Path) -> list[str]:
    logger = get_logger()
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


async def _spawn(args: list[str], owned_by: Path) -> asyncio.subprocess.Process:
    settings = get_settings()
    full_args: list[str] = ["--json", *args, *await _chown_args_for(owned_by)]
    return await spawn_process(
        str(settings.mcmap_binary_path),
        *full_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=MCMAP_STREAM_LIMIT_BYTES,
    )


@asynccontextmanager
async def _run(args: list[str], owned_by: Path) -> AsyncGenerator[MCMapProcess]:
    proc = await _spawn(args, owned_by=owned_by)
    wrapper = MCMapProcess(proc)
    try:
        yield wrapper
    finally:
        await finalize(wrapper.terminate())


@asynccontextmanager
async def download_client(
    version: str, target: Path, *, owned_by: Path
) -> AsyncGenerator[MCMapProcess]:
    async with _run(["download-client", version, str(target)], owned_by) as p:
        yield p


@asynccontextmanager
async def gen_palette(
    packs: list[Path],
    output: Path,
    *,
    level_dat: Path | None,
    owned_by: Path,
) -> AsyncGenerator[MCMapProcess]:
    args: list[str] = ["gen-palette", "-o", str(output)]
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
    mcas: list[Path],
    threads: int,
    *,
    owned_by: Path,
) -> AsyncGenerator[MCMapProcess]:
    args: list[str] = [
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


def _serialize_chunks(chunks: list[tuple[int, int]]) -> str:
    return ";".join(f"{x},{z}" for x, z in chunks)


@asynccontextmanager
async def replace_chunks(
    *,
    source_mca: Path,
    target_mca: Path,
    chunks: list[tuple[int, int]],
    owned_by: Path,
) -> AsyncGenerator[MCMapProcess]:
    if not chunks:
        raise ValueError("replace_chunks requires at least one chunk coord")
    args: list[str] = [
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
    chunks: list[tuple[int, int]],
    owned_by: Path,
) -> AsyncGenerator[MCMapProcess]:
    if not chunks:
        raise ValueError("remove_chunks requires at least one chunk coord")
    args: list[str] = [
        "remove-chunks",
        "-t",
        str(target_mca),
        "-c",
        _serialize_chunks(chunks),
    ]
    async with _run(args, owned_by) as p:
        yield p


@asynccontextmanager
async def prune_inhabited(
    *,
    path: Path,
    threshold_ticks: int,
    mode: Literal["chunks", "regions"],
    dry_run: bool,
    owned_by: Path,
    exclude_ftb_claims: Path | None = None,
) -> AsyncGenerator[MCMapProcess]:
    args: list[str] = [
        "prune-inhabited",
        str(path),
        "--threshold",
        str(threshold_ticks),
        "--mode",
        mode,
    ]
    if dry_run:
        args.append("--dry-run")
    if exclude_ftb_claims is not None:
        args.extend(["--exclude-ftb-claims", str(exclude_ftb_claims)])
    async with _run(args, owned_by) as p:
        yield p


def parse_event_for_test(line: bytes) -> Any:
    return MCMAP_GENERIC_EVENT_ADAPTER.validate_json(line.strip())
