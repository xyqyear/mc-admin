"""Cross-cutting: confirm that MCMapError is the alias for RenderError so existing
imports keep working, and that events from a non-zero exit are surfaced verbatim
to the caller (runner does not raise on its own — orchestrators interpret events)."""

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcmap import runner
from app.mcmap.types import MCMapError, RenderError


@pytest.fixture
def fake_owned_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _write_fake_mcmap(content: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="fake_mcmap_")
    os.close(fd)
    p = Path(path)
    p.write_text(content)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def test_render_error_is_mcmap_error_alias():
    """RenderError must remain importable and be the same class as MCMapError so
    existing call sites (queue.py, tests) don't need to change."""
    assert RenderError is MCMapError
    err = MCMapError("boom")
    assert isinstance(err, RenderError)


async def test_replace_chunks_terminal_error_event_is_surfaced(fake_owned_dir):
    """The runner does not interpret events; error events flow through to the
    consumer. Orchestrators are responsible for raising MCMapError."""
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo \'{"type":"chunk_replaced","x":0,"z":0,"source_kind":"empty"}\'\n'
        'echo \'{"type":"error","message":"unexpected eof"}\'\n'
        "exit 1\n"
    )
    src = fake_owned_dir / "src.mca"
    tgt = fake_owned_dir / "tgt.mca"
    src.write_bytes(b"")
    tgt.write_bytes(b"")
    try:
        with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
            async with runner.replace_chunks(
                source_mca=src,
                target_mca=tgt,
                chunks=[(0, 0)],
                owned_by=fake_owned_dir,
            ) as proc:
                events = [e async for e in proc]
            assert proc.returncode == 1
    finally:
        fake.unlink(missing_ok=True)

    assert events[-1]["type"] == "error"
    assert events[-1]["message"] == "unexpected eof"
