# FTB Claims (`app.ftb_claims`)

Extracts FTB Utilities / FTB Chunks claim data from a server's world directory
and shapes it for the world-restore page's "claims overlay" — coloured polygons
that mark which chunks belong to which player or team, so admins can quickly
roll back a specific player's base after grief reports.

## Pipeline

```
GET /servers/{id}/world-restore/claims
   └─► extract_claims_for_server(data_path)
         ├─ discover_world_root_paths(data_path)           # no dimension scan
         ├─ runner.extract_ftb_claims(world_root, ...)     # mcmap subprocess
         ├─ parse mcmap result.data as a Pydantic payload
         ├─ shape_response(payload, root, data_path)
         │    ├─ resolve each FTB dim folder to a region relpath
         │    ├─ flood-fill each team's claims into clusters
         │    └─ compute centroid / bbox / regions per cluster
         └─► ClaimsResponse
```

`mcmap extract-ftb-claims --world <dir>` autodetects four on-disk formats —
`snbt` (1.16+ FTB Chunks/Teams), `per_team_nbt` (1.7.10 GTNH
ServerUtilities / 1.12.2 FTB Utilities), `universe_dat` (1.10.2 FTB
Utilities 3.x), `latmod_json` (1.7.10 upstream FTBU) — and emits a single
NDJSON `result` event with the unified shape. The backend validates that event
and its `data` payload with `app.mcmap.events` Pydantic models before any
dimension resolution or clustering code runs.

When mcmap can't detect any format, it emits an `error` event with the
message *"could not detect FTB claim format in world directory"*; the runner
maps that to `NoFtbDataError`, which the route turns into
`ClaimsResponse(available=False)` (HTTP 200). Other mcmap errors propagate as
`FtbExtractError` → HTTP 500.

## Caching

Every request re-runs `mcmap extract-ftb-claims`; claim data itself is not
stored. On a real server with ~1500 claims this completes in well under a
second, and the page is admin-only, so the simplicity of "no stored claim
state" outweighs the negligible CPU cost. If a production workload ever shows
otherwise, the right cache key is
`(data_path, content_hash_of_ftb_files)` — not `(data_path, mtime)` because
FTB writes them atomically with the same mtime as the world snapshot.

The route intentionally avoids full world-layout discovery. It only discovers
world root paths from `server.properties` / `level.dat`, then validates the
specific dimension folders reported by mcmap.

## Dimension resolution

`mcmap`'s dim id formats vary by family:

- `snbt` returns ResourceLocations (`minecraft:overworld`, `mythicbotany:alfheim`).
- `per_team_nbt` / `latmod_json` return decimal integer strings (`"0"`,
  `"-1"`, `"7"`) — these are pre-1.13 dim ids.

Every dim entry also carries a `folder` field (path relative to the world
root). The orchestrator safely joins that folder with the primary world root
and `region/`, rejects absolute or parent-traversal paths, and emits a
canonical `region_dir_relpath` when that specific region directory contains at
least one valid MCA file. Otherwise the field is `None` and the cluster keeps
`region_dir_relpath=None` — the frontend renders these clusters but disables
the in-dim selection actions for them. Display labels come from the separate
world-restore dimension-label endpoint used by the layout page.

Direct folder resolution covers root-level legacy/custom dims such as
`<world>/DIM88/region/`, nested modern/modded dims such as
`<world>/dimensions/<modid>/<dim>/region/`, and deeper FTB team dimensions
such as `<world>/dimensions/ftbteamdimensions/team/<uuid>/region/`.

## Clustering

For each `(team, dim)` pair the orchestrator runs a 4-connectivity flood fill
over the team's chunks and emits one `ClusterEntry` per connected component:

- `chunks` — `(cx, cz)` for every chunk in the component.
- `force_loaded` — subset of `chunks` that mcmap flagged with `force_loaded`.
- `centroid_block` — block-space mean `(cx*16+8, cz*16+8)`, ready for the
  frontend's `L.Map.panTo`.
- `bbox_chunk` — `(minCx, minCz, maxCx, maxCz)` for quick label placement.
- `regions` — deduplicated `(cx>>5, cz>>5)` over the cluster's chunks. Used by
  the frontend to expand a cluster into "every region this cluster touches"
  in region selection mode.

Cluster ids are stable across reloads: `f"{team_id}#{region_dir_relpath|_}#{idx}"`.
Two reloads of the same world produce the same cluster set with the same ids,
so the frontend's "fully selected" indicator survives a page refresh.

## Display name fallback

Pre-1.13 FTB families return `team.name = null`. The orchestrator walks
`name → owner.name → members[0].name → team.id[:8]` so the UI never renders
an empty label.

## Subprocess ownership

Mirrors `app.mcmap.runner`: when the backend runs as root, `--chown UID:GID`
is appended so any temp files mcmap writes get chowned back to the data dir's
owner. `extract-ftb-claims` writes output to stdout (no temp files) by
default, so the chown is currently a no-op — kept for parity in case mcmap
gains intermediate spill files in a later version.

The runner is an `@asynccontextmanager` that guarantees `terminate()` on
exit (SIGTERM with 2 s grace, then SIGKILL), identical to the live-map
runner.

## Module layout

```text
app/ftb_claims/
├── __init__.py    # public API: extract_claims_for_server, models, errors
├── models.py      # Pydantic response shapes
├── runner.py      # @asynccontextmanager extract_ftb_claims
├── extract.py     # spawn -> parse -> resolve dims -> flood-fill -> shape
└── cluster.py     # pure 4-connectivity flood-fill, centroid, bbox, regions
```

Tests live in `tests/ftb_claims/`:

- `test_cluster.py` — pure flood-fill correctness (single chunk, L-shape,
  disconnected groups, force-loaded preservation, region dedup, centroid).
- `test_runner.py` — fake-mcmap subprocess (mirrors `tests/mcmap/test_runner.py`).
- `test_extract.py` — end-to-end with a temporary world layout and a fake
  mcmap binary that emits a canned `result` payload; covers dim resolution,
  display-name fallback, the `available=False` branches, and the error
  propagation path.
