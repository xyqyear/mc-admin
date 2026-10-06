import json
from pathlib import Path

import pytest

from app.utils.exec import exec_command
from tests.fixtures.test_utils import (
    OWNER_LABEL,
    OwnedDockerResources,
    owned_docker_resources,  # noqa: F401
)


@pytest.mark.docker
@pytest.mark.parametrize("cache_state", ["existing", "missing"])
async def test_owned_root_container_preserves_existing_owners_and_repairs_tree(
    owned_docker_resources: OwnedDockerResources, cache_state  # noqa: F811
):
    owned = owned_docker_resources
    backend = Path(__file__).resolve().parents[2]
    image = owned.name("ownership-runtime")
    container = owned.name("ownership")
    owned.containers.append(container)
    built = False
    try:
        await exec_command(
            "docker", "build", "--target", "backend-venv", "--label",
            f"{OWNER_LABEL}={owned.owner}", "--tag", image, str(backend.parent),
            timeout=600,
        )
        built = True
        output = await exec_command(
            "docker", "run", "--name", container, "--label", f"{OWNER_LABEL}={owned.owner}",
            "--network", "none", "--user", "0:0", "--tmpfs", "/owned:rw,mode=1777",
            "--mount", f"type=bind,src={backend / 'app'},dst=/app/app,readonly",
            "--mount", f"type=bind,src={backend / 'tests/support/ownership_effects.py'},dst=/app/ownership_effects.py,readonly",
            "--env", "PYTHONDONTWRITEBYTECODE=1", "--entrypoint", "/app/.venv/bin/python",
            image, "/app/ownership_effects.py", cache_state,
            timeout=60,
        )
        report = json.loads(output.splitlines()[-1])
        assert report["before"] == {
            "data": [12345, 23456], "existing": [34567, 45678],
            "existing_file": [34567, 45678], "new": [12345, 23456], "deep": [12345, 23456],
            "cache": [34567, 45678] if cache_state == "existing" else [12345, 23456],
            "tiles": [12345, 23456], "world": [12345, 23456], "region": [12345, 23456],
        }
        assert set(report["after"]) == {
            ".", "existing", "existing/keep.bin", "existing/new", "existing/new/deep",
            "existing/new/deep/created.bin", ".mcmap", ".mcmap/tiles",
            ".mcmap/tiles/world", ".mcmap/tiles/world/region",
        }
        assert all(value == [12345, 23456] for value in report["after"].values())
        assert report["result"] == {"uid": 12345, "gid": 23456}
        assert report["progress"] == 100
        assert report["existing_bytes"] == b"existing bytes\x00\xff".hex()
        assert report["created_bytes"] == b"created bytes\x00\xff".hex()
        assert report["outside_owner"] == [33333, 44444]
        assert report["outside_bytes"] == b"outside bytes\x00\xff".hex()
    finally:
        await owned.remove("container", container)
        if built:
            metadata = json.loads(await exec_command("docker", "image", "inspect", image))[0]
            if metadata["Config"]["Labels"].get(OWNER_LABEL) != owned.owner:
                raise RuntimeError("Refusing to remove an image owned by another test")
            await exec_command("docker", "image", "rm", "--no-prune", metadata["Id"])
