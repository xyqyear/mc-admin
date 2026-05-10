# Dynamic Configuration (`app.dynamic_config`)

Runtime-editable configuration with schema migration. Settings that change behavior of running services (DNS provider credentials, snapshot retention, log-parsing regex, mcmap render parallelism, world-restore tmpdir) live here, not in `config.toml`. Editable through the web UI; persisted in the `DynamicConfig` table; cached in memory; survives schema upgrades.

## Why a separate config layer

`config.toml` is read at process start and never re-read. It's right for things that don't change (database URL, JWT secret, server path). For everything operationally tunable, restarting the service to flip a flag is a non-starter — especially for self-hosted setups where the admin and the operator are the same person clicking around the UI.

## How it stores config

One row per registered config module. The row holds:

- `module_name` — the schema's namespace key (`dns`, `snapshots`, `players`, `log_parser`, `mcmap`)
- `version` — the schema version this row was written against
- `data_json` — the serialized Pydantic model

## Migration on read

When a config row is loaded:

1. Compare stored `version` to `schema_cls.get_schema_version()`.
2. If they differ, run `ConfigMigrator.migrate_config()` — uses Pydantic `model_validate()` to coerce the stored shape, fill in defaults for new fields, drop removed ones.
3. Validate the result through the current schema.
4. Cache the instance.

This means adding/removing/renaming a config field doesn't need a hand-written migration — Pydantic + sensible defaults handle most cases. For genuinely breaking changes, override the migration hook on the schema class.

## Using config in code

`config` is a typed proxy singleton. Property access lazily resolves the cached instance:

```python
from app.dynamic_config import config

if config.snapshots.time_restriction.enabled:
    cutoff = config.snapshots.time_restriction.before_seconds
```

Updates flow through `config_manager.update_config(module_name, new_data)` which validates, persists, and refreshes the cache. The frontend's dynamic-config UI calls this through `/api/config/`.

## Registered modules

In `dynamic_config/configs/`:

- `dns.py` — provider, credentials, managed sub-domain, auto-update flag
- `snapshots.py` — retention, time restrictions, world-restore knobs (tmpdir, disk threshold, preview TTL, janitor interval)
- `players.py` — heartbeat interval, crash threshold, syncer cadence
- `log_parser.py` — regex patterns for join/leave/chat/achievement/uuid/server-stop
- `mcmap.py` — `batch_size`, `thread_count`, `request_timeout_seconds`

## JSON schema → frontend forms

`config_manager.get_module_schema(module_name)` returns the Pydantic JSON Schema for the module. The frontend's `SchemaForm` (rjsf) renders the editor from that schema, so adding a new field on the backend is the only change needed to expose it in the UI.

## Lifespan wiring

`config_manager.initialize_all_configs()` runs in `app.main` lifespan, before any subsystem that depends on config (cron, DNS, players). This guarantees `config.<module>` reads have a real instance, not the schema default.

## Files

- `manager.py` — `ConfigManager`, `register_config()`, `initialize_all_configs()`
- `migration.py` — `ConfigMigrator`
- `schemas.py` — `BaseConfigSchema` (version handling)
- `crud.py` — `DynamicConfig` table CRUD
- `configs/` — one file per registered module
