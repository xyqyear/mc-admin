# Chunk Prune

Chunk pruning removes low-inhabited-time chunks with `mcmap prune-inhabited`.
It is exposed as a server-level workflow with a background preview task and a
separate guarded apply step.

`service.py` orchestrates the workflow; `inputs.py` captures and validates input
versions; `lifecycle.py` retains feature-owned metadata and artifacts;
`execution.py` consumes the adapter stream; `geometry.py` builds map shapes.

## mcmap Contract

The backend calls:

```text
mcmap --json prune-inhabited <server_data_dir> --threshold <ticks> --mode <chunks|regions> [--dry-run] [--exclude-ftb-claims claims.json]
```

`threshold_seconds` from the API is converted to ticks at 20 ticks per second.
The prune root is the server `data/` directory, so mcmap scans every world root
and dimension it can discover under that server.

The supported prune adapter is exactly `mcmap 0.8.4`, checked against the actual
binary. Preview and apply share the same schema version, adapter version,
server generation, confined data path, threshold and mode. A version also hashes
the world file manifest and canonical FTB claims payload. The manifest includes
MCA/MCC files, level metadata and server properties with filesystem identity,
size and modification/change timestamps; `.mcmap` output is excluded. Symlinks
escaping the server data root are rejected. Input capture checks the world
before and after claims extraction to detect concurrent changes.

JSON events are parsed through `app.mcmap.events.MCMAP_PRUNE_EVENT_ADAPTER`.
The mcmap event stream is consumed inside the background task:

- `region_dir` with path and `.mca` count.
- `progress` with phase (`scan` for dry-run, `prune` for apply) and region
  counts.
- `chunks_pruned` in chunk mode as each selected region is discovered, with
  the selected chunks nested under that region.
- `region_pruned` in region mode as each selected region is discovered.
- `result` with scanned/selected totals and FTB-claim skip counters.

Progress events update the generic background task progress. Selected chunk and
region events are accumulated only in memory during a dry-run preview. When the
terminal `result` event arrives, the service merges selected cells into
connected grid-ring shapes and stores that geometry on chunk-prune metadata, not
on the generic background task.

## Preview Lifecycle

`POST /servers/{server_id}/chunk-prune/preview` accepts `threshold_seconds` and
`mode`, then creates a background task. The page reads the current server
workflow through `GET /servers/{server_id}/chunk-prune/state`.

Preview extracts FTB claims once from the primary world root when available and
writes the mcmap-compatible JSON payload into a temp file under the system temp
directory. That file is passed to `--exclude-ftb-claims`, so claimed chunks are
skipped in chunk mode and claimed regions are protected in region mode.

Artifacts live under
`/tmp/mc-admin-world-artifacts/<installation>/prune/<task_id>/`. The registry
retains the actual task projection, geometry, input version and claims file
independently of the generic task center. Dismissing a task does not authorize
artifact deletion or cancel an apply. A successful preview expires after
`prune_preview_ttl_seconds` (default 1,800); the registry retains at most 128
previews and evicts only inactive, unreferenced, ineligible entries. Expiry is
reported explicitly rather than presenting deleted geometry as a valid preview.

The background task result contains the mcmap result fields plus
`threshold_seconds`, `threshold_ticks`, and
`affected_region_counts_by_dimension`. It intentionally does not contain raw
selected chunks/regions or map geometry, so the global task center can list
tasks without serializing large preview payloads.

Completed preview geometry is exposed separately through
`GET /servers/{server_id}/chunk-prune/previews/{task_id}/geometry`. The response
contains one entry per dimension with `unit` (`chunk` or `region`), `cell_count`,
and merged `shapes`. Shape rings are grid coordinates; the frontend multiplies
them by 16 blocks for chunk mode or 512 blocks for region mode before rendering.

## Apply Lifecycle

`POST /servers/{server_id}/chunk-prune/apply` accepts a completed preview task
id. Apply is rejected unless:

- the preview exists for the same server and completed successfully;
- the server is stopped;
- no other world operation lock is active for that server.
- the preview has not expired, become stale or already been consumed;
- current generation, world inputs, claims and the retained claims file still
  match the preview version.

Admission reserves the preview once before asynchronous validation. Concurrent
or repeated apply attempts return HTTP 409 with `prune_preview_consumed`;
expired and changed inputs use `prune_preview_expired` and
`prune_preview_stale`. The accepted worker revalidates under its execution lease
before invoking mcmap, so changes between HTTP acceptance and worker execution
fail safely too. The operation actor is the user who applies the preview.

Apply runs `mcmap prune-inhabited` without `--dry-run` using the same threshold,
mode, server data directory, and claims file captured by the preview. It takes
maintenance, server-data FILES and MAP_CACHE resources atomically with kind
`prune`, so conflicting backup/restore/prune workflows do not overlap. Server
start/up/restart uses the same maintenance ownership and cannot start the JVM
during an apply. mcmap rescans its inputs for apply; it does not execute a frozen
list of preview-selected chunks. The input-version checks detect changes at
admission boundaries but do not fence external tools writing directly to disk.

When mcmap reports affected chunks/regions, the service records affected region
coordinates grouped by `region_dir_relpath`. Finalization closes the prune
worker and invalidates cached PNGs on success, failure or cancellation before
releasing ownership. It starts with the preview's affected coordinates, so
interruption before the first apply event still invalidates possible changes.
Failed cache deletion marks the cache degraded; it is not reported as successful
invalidation. Shared server-operation buttons read the maintenance endpoint;
this page also disables startup immediately while apply is active.

An accepted apply pins its preview until its worker and finite cleanup finish,
including cancellation before worker startup. The janitor checks current
references after asynchronous directory enumeration. Journal recovery references
protect artifacts whose writer termination is unconfirmed. Startup reaps only
owned, unreferenced directories; retained generic task history does not make old
preview geometry or apply authorization valid after restart.

## Frontend Task Shape

The backend does not expose prune-specific SSE. Preview and apply use the
background task manager:

- live progress comes from polling
  `/servers/{server_id}/chunk-prune/state`;
- state returns the latest preview task for the server and the latest apply
  task created after that preview, so starting a new preview hides older apply
  progress/results;
- the optional `preview` state reports `input_version`, `expires_at`,
  `availability` and `apply_task_id`, so the page can distinguish stale, expired
  and consumed previews;
- the global task center uses summary-only `/tasks` list responses;
- the preview overlay is rendered only after the preview task completes;
- switching the map dimension selects a different dimension entry from the same
  completed preview geometry;
- apply progress is shown as task progress, and the map is refreshed after a
  successful apply.

## Dynamic Config

`config.mcmap` owns:

- `prune_default_threshold_seconds` — default value shown in the page, 30
  seconds unless changed by dynamic config.
- `prune_preview_ttl_seconds` — preview validity, default 1,800 seconds with an
  allowed range of 1–86,400 seconds.

Read these values at behavior time. Preview/apply task metadata captures the
threshold/mode used for that task; later dynamic config edits do not rewrite
already-running tasks.
