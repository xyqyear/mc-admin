import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcmap import runner
from app.mcmap.events import MCMAP_FTB_CLAIMS_EVENT_ADAPTER
from tests.support.mcmap import write_fake_mcmap


@pytest.fixture
def fake_owned_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


async def test_extract_reads_large_result_event(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "payload = {\n"
        '    "type": "result",\n'
        '    "detected_format": "snbt",\n'
        '    "teams": 1,\n'
        '    "claims": 0,\n'
        '    "dimensions": 0,\n'
        '    "data": {\n'
        '        "mcmap_extract_ftb_claims_version": 1,\n'
        '        "detected_format": "snbt",\n'
        '        "world_dir": "/tmp/world",\n'
        '        "dimensions": [],\n'
        '        "teams": [\n'
        "            {\n"
        '                "id": "large-result",\n'
        '                "name": "a" * 70000,\n'
        '                "type": "unknown",\n'
        '                "members": [],\n'
        '                "claims": [],\n'
        "            }\n"
        "        ],\n"
        "    },\n"
        "}\n"
        'print(json.dumps(payload, separators=(",", ":")))\n'
    )
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
        async with runner.extract_ftb_claims(
            world_dir=Path("/tmp/world"),
            owned_by=fake_owned_dir,
        ) as proc:
            events = [e async for e in proc.events(MCMAP_FTB_CLAIMS_EVENT_ADAPTER)]
        assert proc.returncode == 0
    fake.unlink()
    assert len(events) == 1
    assert events[0].type == "result"
    assert events[0].data.teams[0].name == "a" * 70000


async def test_extract_yields_error_event(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        'echo \'{"type":"error","message":"could not detect FTB claim format in world directory"}\'\n'
    )
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
        async with runner.extract_ftb_claims(
            world_dir=Path("/tmp/world"),
            owned_by=fake_owned_dir,
        ) as proc:
            events = [e async for e in proc.events(MCMAP_FTB_CLAIMS_EVENT_ADAPTER)]
    fake.unlink()
    assert events[0].type == "error"
    assert "could not detect" in events[0].message
