"""Async context manager wrapping ``mcmap extract-ftb-claims``.

Mirrors the pattern in ``app.mcmap.runner``: spawn with ``--json``, yield a
wrapper that iterates NDJSON events, idempotent ``terminate()`` on exit,
``--chown UID:GID`` appended when running as root.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, List

import aiofiles.os as aioos

from ..config import settings
from ..logger import logger
from ..mcmap.runner import MCMapProcess


async def _chown_args_for(owned_by: Path) -> List[str]:
    if os.geteuid() != 0:
        return []
    try:
        st = await aioos.stat(owned_by)
    except FileNotFoundError:
        logger.warning(
            "ftb-claims: owned_by path %s does not exist; skipping --chown",
            owned_by,
        )
        return []
    return ["--chown", f"{st.st_uid}:{st.st_gid}"]


@asynccontextmanager
async def extract_ftb_claims(
    world_dir: Path,
    *,
    owned_by: Path,
) -> AsyncIterator[MCMapProcess]:
    """Run ``mcmap extract-ftb-claims --world <world_dir>``.

    Format auto-detects (``--format auto``). The wrapper yields the live
    subprocess; callers iterate it to consume the single terminal ``result``
    or ``error`` event.
    """
    args: List[str] = [
        "--json",
        "extract-ftb-claims",
        "--world",
        str(world_dir),
        *await _chown_args_for(owned_by),
    ]
    proc = await asyncio.create_subprocess_exec(
        str(settings.mcmap_binary_path),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    wrapper = MCMapProcess(proc)
    try:
        yield wrapper
    finally:
        await wrapper.terminate()
