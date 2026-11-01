# Minecraft Docker Management (`app.minecraft`)

The bridge between MC Admin and the Docker daemon. Each managed server is one Docker Compose project under `<server_path>/<server_id>/`, running an `itzg/minecraft-server` container. This module owns the compose file format, the lifecycle commands, and the cgroup-v2 / Docker-network metrics.

## Owned adapter

`get_docker_mc_manager()` returns the owning runtime’s adapter, constructed with its server root. It discovers valid server Compose files and returns `MCInstance` objects keyed by server name. Call instances for paths and authoritative state; the Runtime monitoring service owns shared resource samples.

```python
from app.minecraft import get_docker_mc_manager

instance = get_docker_mc_manager().get_instance("survival")
status = await instance.get_status()
```

Use `app.servers.commands.ServerCommands` for user-initiated lifecycle mutations so admission, generation checks and operation history remain enforced.

## `MCInstance`

Per-server façade. Methods fall into three groups:

- **Compose lifecycle**: `create(yaml)`, `up()`, `down()`, `start()`, `stop()`, `restart()`, `remove()`. Existing Compose changes use `app.configuration` preparation and the durable rebuild task, which preserves running intent, validates the expected version and records matching source metadata.
- **State queries**: `exists()`, `created()`, `running()`, plus the hierarchical `MCServerStatus` enum: `REMOVED < EXISTS < CREATED < RUNNING < STARTING < HEALTHY`.
- **File access**: `get_compose_file()`, `get_compose_obj()`, `get_server_properties()`, `get_data_path()`.

Every state-changing method shells out via `ComposeManager.run_compose_command(...)` which wraps `docker compose --project-directory ...`. State queries use the Runtime-owned Docker Engine reader. Structured labels preserve their original values, including equals signs. The reader verifies project, service and directory ownership before using a container.

## Compose file validation

`MCComposeFile` extends a generic `ComposeFile` with Minecraft-specific guarantees enforced by `_verify_compose_yaml()`:

- exactly one service named `mc`
- `image` must be `itzg/minecraft-server` (any tag)
- `container_name` must match `mc-*` (we identify managed containers by label/name)
- `VERSION` env var must be set
- ports / volumes shapes are validated

`MCComposeFile.get_game_version()` returns the `VERSION` env, used by `app.mcmap` to download the matching client jar.

`game_port.py` separates read-only game-target extraction from initialization validation. `get_game_port_mapping()` selects the supported TCP container target `25565` from short or long port mappings; its optional published port is evidence, not the comparison target. `validate_game_port_initialization()` requires explicit matching `SERVER_PORT`, accepts omitted or true `OVERRIDE_SERVER_PROPERTIES`, and accepts omitted or false `SKIP_SERVER_PROPERTIES`. It handles map/list environment forms and rejects unresolved critical values.

Initialization validation runs on reusable template saves and final YAML in `create_server_full()` before resource creation. It does not tighten `MCComposeFile` or existing-server lifecycle/edit/rebuild/adoption paths. Legacy Compose files and template snapshots remain readable without `SERVER_PORT`, and port-conflict scans still include them. There is no bulk migration.

## `ServerProperties`

Read-only Pydantic model parsing `<data>/server.properties`. ~80 optional fields with field validators that coerce difficulty/gamemode int values to canonical strings. Used wherever we need `level-name`, `server-port`, `motd`, etc.

The game-port self-check uses `get_properties_game_port()` to extract only the final `server-port=value` assignment, using the same key/value convention without validating unrelated properties. Blank, missing, Boolean, fractional, or out-of-range values fail comparison instead of defaulting to `25565`. See [self-check](self-check.md) for state handling and remediation.

## Resource monitoring

The Runtime-owned monitor samples host and server resources independently of HTTP requests. See [shared monitoring](monitoring.md) for metric meanings, identity, freshness, scheduling and cleanup. Lifecycle guards always obtain fresh Engine state.

## Files

- `manager.py` — `DockerMCManager` (multi-instance facade)
- `instance.py` — `MCInstance`
- `compose.py` — `MCComposeFile` (Minecraft-specific compose wrapper)
- `game_port.py` — game target/properties extraction and scoped initialization validation
- `properties.py` — `ServerProperties` parser
- `utils.py` — small async helpers
- `docker/manager.py` — Compose lifecycle and execution commands
- `docker/compose_file.py` — generic `ComposeFile` model
- `docker/reader.py` — owned Engine reads, project identity and Java process discovery
- `status.py` — shared lifecycle states
- `docker/cgroup.py` — cgroup v2 parsers
- `docker/network.py` — Docker network stats
