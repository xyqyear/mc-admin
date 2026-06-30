# Chunk Prune

Chunk pruning removes low-inhabited-time chunks with `mcmap prune-inhabited`.
It is exposed as a server-level workflow with a background preview task and a
separate guarded apply step.

## mcmap Contract

The backend calls:

```text
mcmap --json prune-inhabited <server_data_dir> --threshold <ticks> --mode <chunks|regions> [--dry-run] [--exclude-ftb-claims claims.json]
```

`threshold_seconds` from the API is converted to ticks at 20 ticks per second.
The prune root is the server `data/` directory, so mcmap scans every world root
and dimension it can discover under that server.

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
region events are accumulated only in memory during a dry-run preview and are
attached to the final task result, grouped by data-relative `region/` directory.

## Preview Lifecycle

`POST /servers/{server_id}/chunk-prune/preview` accepts `threshold_seconds` and
`mode`, then creates a background task whose task id can be polled through
`/tasks/{task_id}`.

Preview extracts FTB claims once from the primary world root when available and
writes the mcmap-compatible JSON payload into a temp file under the system temp
directory. That file is passed to `--exclude-ftb-claims`, so claimed chunks are
skipped in chunk mode and claimed regions are protected in region mode.

The background task result contains the mcmap result fields plus
`threshold_seconds`, `threshold_ticks`, `affected_regions_by_dimension`, and
dry-run-only `dimensions`. Each dimension entry contains `region_dir_relpath`
and the selected chunk or region geometry for that dimension. The frontend uses
that terminal result to render the selected dimension's preview overlay once.

## Apply Lifecycle

`POST /servers/{server_id}/chunk-prune/apply` accepts a completed preview task
id. Apply is rejected unless:

- the preview exists for the same server and completed successfully;
- the server is stopped;
- no other world operation lock is active for that server.

Apply runs `mcmap prune-inhabited` without `--dry-run` using the same threshold,
mode, server data directory, and claims file captured by the preview. It takes
the per-server operation lock with kind `prune`, so backup/restore/prune
workflows do not overlap.

When mcmap reports affected chunks/regions, the service records affected region
coordinates grouped by `region_dir_relpath`. After a successful apply it deletes
cached map PNGs for those regions so future map views render from the changed
MCA files.

## Frontend Task Shape

The backend does not expose prune-specific SSE. Preview and apply use the
generic task API:

- live progress comes from `/tasks/{task_id}` polling;
- the preview overlay is rendered only after the preview task completes;
- switching the map dimension selects a different dimension entry from the same
  completed preview result;
- apply progress is shown as task progress, and the map is refreshed after a
  successful apply.

## Dynamic Config

`config.mcmap` owns:

- `prune_default_threshold_seconds` — default value shown in the page, 30
  seconds unless changed by dynamic config.

Read these values at behavior time. Preview/apply task metadata captures the
threshold/mode used for that task; later dynamic config edits do not rewrite
already-running tasks.
