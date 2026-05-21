# Server Map (`app.mcmap`)

On-demand world rendering driven by the [mcmap](https://github.com/xyqyear/mcmap) CLI. The system answers HTTP requests for individual map tiles (`r.X.Z.png`) by lazily rendering Minecraft region files (`r.X.Z.mca`) into PNGs, with a per-server filesystem cache and tight cancellation semantics so abandoned tiles never waste rendering work.

## Why tiles, not whole-world snapshots

Minecraft worlds are sparse and unbounded. Pre-rendering everything wastes disk and CPU on regions a user will never view. A tile-on-demand pipeline turns map browsing into a per-region render, which composes naturally with HTTP caching and Leaflet's tile model on the frontend.

## Cache layout

All artifacts live under `data/.mcmap/` per server. The directory is excluded from Restic backups: every byte is regenerable from the world plus the Minecraft client jar.

```
data/.mcmap/
├── client.jar              # Minecraft client jar for the server's version
├── palette.json            # block → color palette for that version + mod set
├── palette.hash            # SHA256 fingerprint, see "Palette currency"
└── tiles/<region_path>/    # rendered PNGs, mirroring r.X.Z.mca filenames
```

`<region_path>` is the dimension's region folder relative to `data/`, e.g. `world/region`, `world_nether/DIM-1/region`, `world/dimensions/minecraft/the_end/region`. Hard isolation by dimension (see "Render queue") keeps each dimension's tiles in its own subfolder.

## Initialization

`POST /servers/{id}/map/initialize` runs a two-stage SSE flow:

1. **Client jar** — `mcmap download-client <version> client.jar`. The version comes from the server's compose (`docker-minecraft-server` `VERSION` env var). Cached fast-path if `client.jar` exists.
2. **Palette** — `mcmap gen-palette --level-dat <data>/<level-name>/level.dat -p <mods_dir?> -p client.jar -o palette.json`. The backend always passes `--level-dat` when the file exists; mcmap auto-picks 1.7.10 / 1.12.2 / 1.13+ pipelines from its content (and ignores it for 1.13+). Mods directory is included as an extra pack when `data/mods/` contains at least one `.jar`.

Both stages stream NDJSON progress events through to the browser as SSE.

### Palette currency

The palette is invalidated when its inputs change. The fingerprint is `SHA256(version + sorted(mod_jar_filenames))`, written to `palette.hash`. Inputs deliberately exclude `level.dat` — its mtime updates every world tick, which would force needless palette regeneration. The mod set already determines the FML registry that pre-1.13 worlds care about.

## Tile freshness

mcmap renders with `--preserve-mtime`, stamping each output PNG with its source MCA's mtime. Freshness check: `mca.mtime == png.mtime`. Any divergence (missing PNG, stale PNG, missing MCA) routes the request appropriately:

- `missing_mca` → HTTP 404
- `missing_png` or `stale` → enqueue render, await PNG, serve

Tile URLs include `?mt=<mca_mtime>` so the browser HTTP cache busts automatically when the MCA changes.

## Render queue

A `ServerRenderQueue` exists per `(server_id, region_path)` pair. Including `region_path` in the key guarantees a single `mcmap render --split` invocation never mixes regions from different dimensions, so PNGs always land in the correct subfolder.

**Batching**: a worker collects up to `batch_size` pending coordinates and runs them in one `mcmap render --split --preserve-mtime -j <thread_count>` invocation. The subprocess streams a `region` NDJSON event per output; the worker resolves each waiter's future as the matching event arrives. Any region the subprocess never emits (e.g. terminated mid-batch) gets a `RenderError`.

**Coalescing**: duplicate `(x, z)` requests share one `asyncio.Future`. The consumer's `await` is wrapped in `asyncio.shield` so cancelling one consumer does not disturb others.

**Cancellation**: when the last consumer for a coordinate disconnects, the entry drops from the queue. If the running batch becomes empty as a result, the mcmap subprocess is killed (SIGTERM, then SIGKILL after 2 s). This propagates browser-side abort all the way to terminating the renderer.

**Idle timeout**: the worker exits after 60 s without work; the next request respawns it.

## Subprocess ownership

mcmap runs with the backend's privileges — there is no setuid demotion. When the backend runs as root, `_chown_args_for(owned_by)` resolves the owner of `data_path` via `os.stat` and appends `--chown UID:GID`. mcmap then chowns every file/directory it creates or atomically replaces back to that owner. mcmap rejects `--chown` unless euid is 0, so the flag is omitted for non-root backends and outputs land as the backend's uid.

## Region-path safety

`region_path` is request-scoped — it's a query parameter on every map endpoint and is never persisted in the database or config. `_resolve_region_path()` rejects absolute paths and any input that resolves outside `data/` (traversal). The frontend tracks the selected dimension in component state and threads it through every request.

## Dimension discovery

`GET /dimensions` projects the cached `app.world.layout` discovery into the
mcmap response shape. Region paths remain relative to `data/`, while labels
come from the shared `app.world.dimension_labels` rules used by world restore:
Overworld for the world root, Nether/End for `DIM-1`/`DIM1`, vanilla names for
`dimensions/minecraft/*`, and the world-root-relative dimension path without a
leading `dimensions/` for custom modded dimensions.

## Settings

- Static (`config.toml` / env): `mcmap_binary_path` (default `/usr/local/bin/mcmap`).
- Dynamic (`mcmap` schema): `batch_size`, `thread_count`, `request_timeout_seconds`.

## Endpoints

Mounted under `/api/servers/{server_id}/map/`:

- `GET /status` — initialization state + game version
- `GET /dimensions` — auto-discovered region folders from `app.world.layout`, with shared world-restore dimension labels
- `GET /regions?region=<rel-path>` — `[x, z, mtime]` triples from `app.world.region_manifest` for every non-empty regular `r.X.Z.mca` (frontend skips HTTP for absent regions; mtime is appended to tile URLs as `?mt=`)
- `POST /initialize` — two-stage SSE
- `GET /tiles/{x}/{z}.png?region=<rel-path>` — tile fetch (404 missing MCA, 409 not initialized, 503 render timeout)
- `DELETE /cache?region=<rel-path>` — wipes one dimension's tiles
