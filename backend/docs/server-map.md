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

`POST /servers/{id}/map/initialize?force=true` first deletes `client.jar`,
`palette.json`, and `palette.hash`, then runs the same flow. Use it when the
cached prerequisites may be corrupt or tied to the wrong client.

Both stages validate mcmap NDJSON with command-specific Pydantic event models,
then stream progress through to the browser as SSE.
Failure events retain the same stage/phase shape and use safe Chinese messages.
Raw adapter error events, stderr and configuration exception values are excluded
from SSE and application logs; diagnostics retain exception types and frame locations.

### Palette currency

The palette is invalidated when its inputs change. The fingerprint is `SHA256(version + sorted(mod_jar_filenames))`, written to `palette.hash`. Inputs deliberately exclude `level.dat` — its mtime updates every world tick, which would force needless palette regeneration. The mod set already determines the FML registry that pre-1.13 worlds care about.

## Tile freshness

mcmap renders with `--preserve-mtime`, stamping each output PNG with its source MCA's mtime. Freshness check: `mca.mtime == png.mtime`. Any divergence (missing PNG, stale PNG, missing MCA) routes the request appropriately:

- `missing_mca` → HTTP 404
- `missing_png` or `stale` → enqueue render, await PNG, serve

Tile URLs include `?mt=<mca_mtime>` so the browser HTTP cache busts automatically when the MCA changes.

## Render queue

A `ServerRenderQueue` exists per `(server_id, region_path)` pair. Including `region_path` in the key guarantees a single `mcmap render --split` invocation never mixes regions from different dimensions, so PNGs always land in the correct subfolder.

**Batching**: a worker collects up to `batch_size` pending coordinates and runs them in one `mcmap render --split --preserve-mtime -j <thread_count>` invocation. The queue reads `config.mcmap` for each batch, so dynamic config edits affect the next render invocation without rebuilding the queue. The subprocess streams a validated `region` event per output; the worker publishes each result after the child and its cleanup have stopped. Any region the subprocess never emits gets a `RenderError`; completed regions retain their individual results.

**Coalescing**: duplicate `(x, z)` requests share one `asyncio.Future`. The consumer's `await` is wrapped in `asyncio.shield` so cancelling one consumer does not disturb others.

**Cancellation**: when the last consumer for a coordinate disconnects, the entry drops from the queue. If the batch becomes empty, its task is cancelled even while waiting for a cache lease. An already running child is stopped with SIGTERM and then SIGKILL after 2 s. The batch retains ownership through process cleanup and removal of incomplete PNGs. Unconfirmed writers preserve their output and mark the cache degraded for explicit recovery.

The runner drains stderr concurrently with streamed JSON output and retains only its final 256 KiB. A noisy renderer cannot block its stdout progress by filling the stderr pipe. Concurrent termination requests share one cleanup task, which stops the stderr reader before handing both pipes to the process finalizer; pipe readers and the child are settled before cleanup returns.

**Idle timeout**: the worker exits after 60 s without work; the next request respawns it.

## Subprocess ownership

mcmap runs with the backend's privileges — there is no setuid demotion. When the backend runs as root, `_chown_args_for(owned_by)` resolves the owner of `data_path` via `os.stat` and appends `--chown UID:GID`. mcmap then chowns every file/directory it creates or atomically replaces back to that owner. mcmap rejects `--chown` unless euid is 0, so the flag is omitted for non-root backends and outputs land as the backend's uid.

## Region-path safety

`region_path` is request-scoped — it's a query parameter on every map endpoint and is never persisted in the database or config. `_resolve_region_path()` rejects absolute paths and any input that resolves outside `data/` (traversal). The frontend tracks the selected dimension in component state and threads it through every request.

## Settings

- Static (`config.toml` / env): `mcmap_binary_path`, otherwise startup discovery from `PATH`, `/usr/local/bin/mcmap`, then `/usr/bin/mcmap`.
- Dynamic (`mcmap` schema): `batch_size`, `thread_count`, `request_timeout_seconds`.

## Endpoints

Mounted under `/api/servers/{server_id}/map/`:

- `GET /status` — initialization state + game version
- `GET /regions?region=<rel-path>` — `[x, z, mtime]` triples from `app.world.region_manifest` for every non-empty regular `r.X.Z.mca` (frontend skips HTTP for absent regions; mtime is appended to tile URLs as `?mt=`)
- `POST /initialize?force=<bool>` — two-stage SSE; force clears prerequisites first
- `GET /tiles/{x}/{z}.png?region=<rel-path>` — tile fetch (404 missing MCA, 409 not initialized, 503 render timeout)

## Deletion admission

Map initialization retains request-scoped write admission through SSE closure. Tile requests, queued consumers and active render batches participate in the same deletion gate. A disconnected final consumer may release its request, but the worker retains admission until subprocess/cache cleanup finishes. Deletion rejects active map writers and new map writes during its freeze.

Each actual render batch owns a durable `map_render` operation and a `MAP_CACHE`
claim for its server generation and region directory. Initialization owns
`map_initialize` and the server cache root, including prerequisite deletion,
downloads and palette hash publication. Terminal initialization SSE events follow
cleanup and settlement. Workers detach from the requesting operation so background
rendering cannot reuse a finished request's journal context.

Cache writers also declare their concrete `FILES` paths in the same atomic lease:
`data/.mcmap/tiles/<region>` for rendering and `data/.mcmap` for initialization.
Ordinary file edits or archive extraction into those paths therefore observe the
same exclusion as world cache invalidation, without locking unrelated data files.

The coordinator acquires the complete batch scope atomically. Renderers hold no
maintenance lease while waiting for world restore/prune cache ownership. Separate
dimension caches can render concurrently; world mutation and cache invalidation
wait for overlapping render writers. Existing fresh PNG reads need no cache lease.
Queued writers recheck generation and cache recovery state after acquisition.

World-preview queues supply a `PreviewRenderTarget` with the real server identity,
generation and artifact session. Staged MCA input and PNG output are confined to
that session directory; they are not represented as files inside the live server
project. Each batch records `world_preview_render`, retains its `world_preview`
recovery reference and uses a distinct preview cache claim plus the live palette's
exact file claim. World cache-root operations still exclude these preview renders,
and palette initialization waits for palette readers. Generation is checked before
starting a child; unknown writers retain the artifact reference and partial output.
