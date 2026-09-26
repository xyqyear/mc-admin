import json
import time
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest

from tests.support.collection import digest


class TimingRecorder:
    def __init__(self, output: Path, manifest: Callable[[pytest.Session], dict[str, Any]]) -> None:
        self.output = output
        self.manifest = manifest
        self.started = time.perf_counter()
        self.phases: list[dict[str, Any]] = []
        self.collection_errors: list[str] = []

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        event = {"nodeid": report.nodeid, "phase": report.when, "outcome": report.outcome,
                 "duration_seconds": report.duration}
        if hasattr(report, "wasxfail"):
            event["wasxfail"] = str(report.wasxfail)
        self.phases.append(event)

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed:
            self.collection_errors.append(report.nodeid)

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_sessionfinish(self, session: pytest.Session) -> Generator[None]:
        completed = False
        try:
            yield
            completed = True
        finally:
            manifest = self.manifest(session)
            document = {"schema_version": 1, "manifest_sha256": digest(manifest), "completed": completed,
                        "exit_status": int(session.exitstatus), "session_seconds": time.perf_counter() - self.started,
                        "collection_errors": self.collection_errors, "phases": self.phases}
            self.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.output.with_suffix(self.output.suffix + ".tmp")
            temporary.write_text(json.dumps(document, indent=2) + "\n")
            temporary.replace(self.output)
