import asyncio
import json
import os
import shutil
import subprocess
import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest

from tests.support.collection import digest, validate_plan
from tests.support.environment import configure_test_environment
from tests.support.timing import TimingRecorder

# Collection has an explicit owner separate from every test runtime.
_environment = configure_test_environment()
_inventory: pytest.StashKey[list[dict[str, Any]]] = pytest.StashKey()
_binary_environment = {
    "fd": "FD_BINARY_PATH",
    "restic": "RESTIC_BINARY_PATH",
    "mcmap": "MCMAP_BINARY_PATH",
    "7z": None,
}


_collection_runtime: pytest.StashKey[Any] = pytest.StashKey()
_collection_binding: pytest.StashKey[Any] = pytest.StashKey()
_plan: pytest.StashKey[dict[str, Any]] = pytest.StashKey()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "shard_group(name): keep files sharing a fixture boundary in one CI shard")
    path, index = config.getoption("--test-plan"), config.getoption("--test-shard")
    if bool(path) != (index is not None) or (path and config.getoption("--test-group")):
        raise pytest.UsageError("--test-plan and --test-shard require each other and cannot combine with --test-group")
    if path:
        config.stash[_plan] = json.loads(Path(path).read_text())
    output = config.getoption("--timing-report")
    if output:
        config.pluginmanager.register(TimingRecorder(Path(output), collection_manifest), "mc-admin-timing")


def pytest_sessionstart(session: pytest.Session) -> None:
    from app.runtime import Runtime

    runtime = Runtime()
    binding = runtime.bind()
    binding.__enter__()
    session.config.stash[_collection_runtime] = runtime
    session.config.stash[_collection_binding] = binding


def pytest_sessionfinish(session: pytest.Session) -> None:
    runtime = session.config.stash.get(_collection_runtime, None)
    binding = session.config.stash.get(_collection_binding, None)
    try:
        if runtime is not None:
            asyncio.run(runtime.close())
    finally:
        if binding is not None:
            binding.__exit__(None, None, None)
    _environment.cleanup()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("mc-admin test isolation")
    group.addoption("--run-docker", action="store_true", help="Enable owned Docker tests")
    group.addoption("--run-external", action="store_true", help="Enable external service tests")
    group.addoption("--require-capabilities", action="store_true", help="Fail on missing declared binaries")
    group.addoption("--test-group", help="Select a collected first-level test group")
    group.addoption("--collection-manifest", help="Write collected and selected test identities as JSON")
    group.addoption("--test-plan", help="Use the immutable collected CI shard plan")
    group.addoption("--test-shard", type=int, help="Select a one-based shard from --test-plan")
    group.addoption("--timing-report", help="Write exact setup/call/teardown durations and execution outcomes")


def capabilities(item: pytest.Item) -> list[str]:
    values = {name for name in ("docker", "external") if item.get_closest_marker(name)}
    for mark in item.iter_markers("binary"):
        if len(mark.args) != 1 or mark.args[0] not in _binary_environment or mark.kwargs:
            raise pytest.UsageError(f"{item.nodeid}: binary requires one known binary name")
        values.add(mark.args[0])
    return sorted(values)


def test_group(item: pytest.Item) -> str:
    relative = item.path.relative_to(Path(__file__).parent)
    return relative.parts[0] if len(relative.parts) > 1 else "root"


def shard_groups(item: pytest.Item) -> list[str]:
    names = set()
    for mark in item.iter_markers("shard_group"):
        if len(mark.args) != 1 or not isinstance(mark.args[0], str) or not mark.args[0].strip() or mark.kwargs:
            raise pytest.UsageError(f"{item.nodeid}: shard_group requires one nonempty group name")
        names.add(mark.args[0])
    return sorted(names)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> Generator[None]:
    config.stash[_inventory] = [
        {"nodeid": item.nodeid, "group": test_group(item), "capabilities": capabilities(item),
         "shard_groups": shard_groups(item)}
        for item in items
    ]
    selected, deselected = [], []
    for item in items:
        required = capabilities(item)
        excluded = (
            ("docker" in required and not config.getoption("--run-docker"))
            or ("external" in required and not config.getoption("--run-external"))
            or (config.getoption("--test-group") not in (None, test_group(item)))
        )
        (deselected if excluded else selected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
    yield
    value = config.stash.get(_plan, None)
    if value is not None:
        manifest = {"collected": config.stash[_inventory], "selected": [item.nodeid for item in items],
                    "policy": collection_policy(config)}
        try:
            validate_plan(manifest, value)
            index = config.getoption("--test-shard")
            if not isinstance(index, int) or not 1 <= index <= value["shard_count"]:
                raise ValueError("Selected shard is outside the plan")
            wanted = set(value["shards"][index - 1]["nodeids"])
        except ValueError as error:
            raise pytest.UsageError(str(error)) from error
        remaining = [item for item in items if item.nodeid not in wanted]
        items[:] = [item for item in items if item.nodeid in wanted]
        config.hook.pytest_deselected(items=remaining)
    if config.getoption("--require-capabilities") and not config.option.collectonly:
        for name in {name for item in items for name in capabilities(item)}:
            if name in _binary_environment and not binary_path(name):
                raise pytest.UsageError(f"Selected tests require missing binary: {name}")


def collection_policy(config: pytest.Config) -> dict[str, Any]:
    return {"docker": config.getoption("--run-docker"), "external": config.getoption("--run-external"),
            "group": config.getoption("--test-group"), "expression": config.option.markexpr,
            "keyword": config.option.keyword}


def collection_manifest(session: pytest.Session) -> dict[str, Any]:
    result = {"collected": session.config.stash.get(_inventory, []),
              "selected": [item.nodeid for item in session.items], "policy": collection_policy(session.config)}
    value = session.config.stash.get(_plan, None)
    if value is not None:
        result.update({"plan_sha256": digest(value), "shard": session.config.getoption("--test-shard")})
    return result


def pytest_collection_finish(session: pytest.Session) -> None:
    output = session.config.getoption("--collection-manifest")
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(collection_manifest(session), indent=2) + "\n")


def binary_path(name: str) -> str | None:
    variable = _binary_environment[name]
    return shutil.which(os.environ.get(variable, name) if variable else name)


@pytest.fixture(autouse=True)
async def isolated_runtime(tmp_path_factory: pytest.TempPathFactory) -> AsyncGenerator[Any]:
    from app.config import Settings
    from app.main import api_app, app
    from app.runtime import Runtime

    runtime_root = tmp_path_factory.mktemp("runtime")
    for directory in ("servers", "archives", "logs"):
        (runtime_root / directory).mkdir()
    settings = Settings(  # type: ignore
        server_path=runtime_root / "servers", archive_path=runtime_root / "archives",
        logs_dir=runtime_root / "logs", database_url=f"sqlite+aiosqlite:///{runtime_root / 'runtime.sqlite3'}",
    )
    runtime = Runtime(settings)
    with runtime.bind(), pytest.MonkeyPatch.context() as patch:
        patch.setattr(app.state, "runtime", runtime)
        patch.setattr(api_app.state, "runtime", runtime)
        yield runtime
        await runtime.close()


@pytest.fixture(autouse=True, scope="session")
def owned_archive_scratch_path() -> Generator[None]:
    from app.archive import uploads

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(uploads, "ARCHIVE_UPLOAD_TMP_DIR", Path(_environment.name) / "uploads")
        yield


@pytest.fixture(autouse=True)
def capability_guard(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    required = capabilities(request.node)
    for name in required:
        if name in _binary_environment and not binary_path(name):
            pytest.skip(f"Declared capability unavailable: {name}")
    if "docker" in required and request.config.getoption("--run-docker"):
        return
    original = subprocess.Popen

    def guarded_popen(args: Any, *positional: Any, **kwargs: Any) -> Any:
        command = args if isinstance(args, (str, bytes, os.PathLike)) else args[0]
        executable = os.fsdecode(command)
        if (
            not isinstance(args, (str, bytes, os.PathLike)) and len(args) >= 4
            and Path(executable).resolve() == Path(sys.executable).resolve()
            and Path(os.fsdecode(args[1])).resolve() == Path(__file__).resolve().parents[1] / "app/operations/process_gate.py"
        ):
            executable = os.fsdecode(args[3])
        name = Path(executable).name
        if name == "docker":
            raise RuntimeError("Docker requires @pytest.mark.docker and --run-docker")
        if name in _binary_environment and name not in required:
            resolved = shutil.which(executable)
            if resolved is not None and resolved == binary_path(name):
                raise RuntimeError(f"Real {name} execution requires @pytest.mark.binary({name!r})")
        return original(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded_popen)

    import docker

    def guarded_client(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Docker requires @pytest.mark.docker and --run-docker")

    monkeypatch.setattr(docker, "APIClient", guarded_client)
    monkeypatch.setattr(docker, "DockerClient", guarded_client)
    monkeypatch.setattr(docker, "from_env", guarded_client)
