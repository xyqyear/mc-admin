# Minecraft Docker Management (`app.minecraft`)

The bridge between MC Admin and the Docker daemon. Each managed server is one Docker Compose project under `<server_path>/<server_id>/`, running an `itzg/minecraft-server` container. This module owns the compose file format, the lifecycle commands, and the cgroup-v2 / Docker-network metrics.

## Singleton

`docker_mc_manager` (created from `settings.server_path`) is the entry point. It returns `MCInstance` objects keyed by server name and aggregates info across all of them.

```python
from app.minecraft import docker_mc_manager

instance = docker_mc_manager.get_instance("survival")
await instance.start()
```

## `MCInstance`

Per-server façade. Methods fall into three groups:

- **Compose lifecycle**: `create(yaml)`, `update_compose_file(yaml)`, `up()`, `down()`, `start()`, `stop()`, `restart()`, `remove()`.
- **State queries**: `exists()`, `created()`, `running()`, plus the hierarchical `MCServerStatus` enum: `REMOVED < EXISTS < CREATED < RUNNING < STARTING < HEALTHY`.
- **File access**: `get_compose_file()`, `get_compose_obj()`, `get_server_properties()`, `get_data_path()`.

Every state-changing method shells out via `ComposeManager.run_compose_command(...)` which wraps `docker compose --project-directory ...`. Reads happen via docker-py.

## Compose file validation

`MCComposeFile` extends a generic `ComposeFile` with Minecraft-specific guarantees enforced by `_verify_compose_yaml()`:

- exactly one service named `mc`
- `image` must be `itzg/minecraft-server` (any tag)
- `container_name` must match `mc-*` (we identify managed containers by label/name)
- `VERSION` env var must be set
- ports / volumes shapes are validated

`MCComposeFile.get_game_version()` returns the `VERSION` env, used by `app.mcmap` to download the matching client jar.

## `ServerProperties`

Read-only Pydantic model parsing `<data>/server.properties`. ~80 optional fields with field validators that coerce difficulty/gamemode int values to canonical strings. Used wherever we need `level-name`, `server-port`, `motd`, etc.

## Resource monitoring

- **Memory** (`docker/cgroup.py`): parses cgroup v2 `memory.stat` into `MemoryStats` (anon, file, kernel, …). Derived properties: `total_memory`, `active_memory`, `inactive_memory`.
- **Block I/O**: `BlockIODevice` per device — `rbytes`, `wbytes`, `rios`, `wios`, derived `total_bytes` / `total_operations`.
- **Network** (`docker/network.py`): `NetworkStats` with rx/tx bytes & packets.
- **CPU**: `app.utils.system.get_process_cpu_usage()` (psutil-backed, run via `asyncio.to_thread`).

`get_running_server_names()` cheap-checks `docker ps` filtered by the `mc-*` container-name prefix; per-server stats only fan out to servers we know are running.

## Files

- `manager.py` — `DockerMCManager` (multi-instance facade)
- `instance.py` — `MCInstance`
- `compose.py` — `MCComposeFile` (Minecraft-specific compose wrapper)
- `properties.py` — `ServerProperties` parser
- `utils.py` — small async helpers
- `docker/manager.py` — generic `ComposeManager` and `DockerManager`
- `docker/compose_file.py` — generic `ComposeFile` model
- `docker/cgroup.py` — cgroup v2 parsers
- `docker/network.py` — Docker network stats
