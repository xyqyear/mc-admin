# Dynamic Configuration (`app.dynamic_config`)

Runtime-editable configuration with schema migration. Settings that change behavior of running services (DNS provider credentials, snapshot retention, log-parsing regex, mcmap render parallelism, world layout discovery, world-restore preview behavior, self-check thresholds) live here, not in `config.toml`. Editable through the web UI; persisted in the `DynamicConfig` table; cached in memory; survives schema upgrades.

## Startup and editable settings

`config.toml` supplies startup settings such as the database URL, JWT secret and server path. Operational settings in the registered dynamic modules are editable through the API and UI while the application runs.

## How it stores config

One row per registered config module. The row holds:

- `module_name` — the schema's namespace key (`dns`, `snapshots`, `players`, `log_parser`, `mcmap`, `world`, `self_check`)
- `config_schema_version` — the schema version this row was written against
- `config_data` — the serialized configuration

## Migration on read

When a config row is loaded:

1. Compare stored `config_schema_version` to `schema_cls.get_schema_version()`.
2. If they differ, run `ConfigMigrator.migrate_config()` — uses Pydantic `model_validate()` to coerce the stored shape, fill in defaults for new fields, drop removed ones.
3. Validate the result through the current schema.
4. Cache the instance.

Compatible field changes use Pydantic validation and defaults. Renames or incompatible changes require an explicit compatibility decision; model validation does not infer renamed fields.

## Using config in code

`get_config()` returns the active runtime’s typed `ConfigProxy` view. The view captures its owning `ConfigManager` when constructed; each property reads that manager’s current cached instance. Holding a view across another runtime’s binding never redirects its reads:

```python
from app.dynamic_config import get_config

config = get_config()
if config.snapshots.time_restriction.enabled:
    cutoff = config.snapshots.time_restriction.before_seconds
```

Updates flow through `get_config_manager().update_config(module_name, new_data)` which validates, persists, and refreshes the cache. The frontend's dynamic-config UI calls this through `/api/config/`.

The view has seven explicit properties: `dns`, `snapshots`, `log_parser`,
`players`, `mcmap`, `world` and `self_check`. A held view observes a successfully
replaced cached model on its next property read. Reading before the owning manager
has initialized raises an error. Acquiring the view through `get_config()` requires
an explicitly bound runtime; subsequent property reads use its captured manager.

After structural validation, `BaseConfigSchema.validate_update()` checks domain rules for newly submitted settings before persistence. Log-parser settings compile each pattern and require the capture groups used by the parser: UUID and achievement need two, join and leave need one, chat needs three, and stop needs none. Invalid submissions preserve the existing cache and stored configuration. The write-only check leaves legacy loading unchanged, so an administrator can still open settings to repair previously stored invalid rules.

Runtime-tunable values are read at the point of behavior. Subsystems that cache
derived state use an explicit refresh/rebuild path.

## Registered modules

In `dynamic_config/configs/`:

- `dns.py` — provider, credentials, managed sub-domain and enabled flag
- `snapshots.py` — retention, time restrictions, world-restore knobs (preview TTL, janitor interval, preview region-size estimate)
- `players.py` — heartbeat interval, crash threshold, syncer cadence, skin fetch timeout, ignored player-name prefixes (default `["bot_"]`)
- `log_parser.py` — regex patterns for join/leave/chat/achievement/uuid/server-stop
- `mcmap.py` — `batch_size`, `thread_count`, `request_timeout_seconds`
- `world.py` — region stat workers, dimension scan depth, dimension labels
- `self_check.py` — per-check toggles, thresholds, retained-run retention, event-trigger switches

## JSON schema → frontend forms

`get_config_manager().get_schema_info(module_name)` returns the Pydantic JSON Schema for the module. The frontend's rjsf form renders the editor from that schema; domain validation remains at the server's save boundary.

## Lifespan wiring

`Runtime.start()` initializes its configuration manager before cron, DNS and players. `runtime_factories.py` constructs the manager with the owner’s database session factory and registers the schemas. Updates always use this captured factory, even when another runtime is bound. Behavior reads use the current cached model; clients that derive reusable state, such as DNS connections, explicitly refresh that state. No module-level configuration object or fallback runtime is created.

## Files

- `manager.py` — `ConfigManager`, its explicit session factory and runtime accessor
- `models.py` — the persisted `DynamicConfig` table
- `api_models.py` — configuration HTTP request and response DTOs
- `__init__.py` — the typed view and `get_config()`
- `migration.py` — `ConfigMigrator`
- `schemas.py` — `BaseConfigSchema` (version handling)
- `crud.py` — `DynamicConfig` table CRUD
- `configs/` — one file per registered module
