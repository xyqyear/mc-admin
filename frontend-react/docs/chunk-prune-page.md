# Chunk Prune Page

The chunk-prune page is mounted at `/server/:id/chunk-prune`. It shares the
same Leaflet map, world layout queries, FTB-claims overlay, and player-location
overlay used by the world-restore page, but the map itself is read-only: the
only selection layer is the prune preview overlay.

## Page Layout

The header mirrors the world-restore map page:

- map refresh;
- force reload of map prerequisites;
- dimension select;
- map help;
- server tag.

The main content is a two-column layout: full map on the left, compact side
panel on the right. The side panel has tabs for prune controls, claims, and
player locations. The claims and player tabs use the shared map-layer list
components; the claims list disables restore-specific select buttons on this
page.

## Threshold And Mode

The prune tab exposes:

- numeric threshold input;
- unit select (`seconds`, `minutes`, `hours`);
- chunk/region mode tabs;
- preview/cancel/apply actions;
- progress cards for preview and apply.

The default threshold comes from
`GET /servers/{id}/chunk-prune/settings`, backed by
`mcmap.prune_default_threshold_seconds`. Values are sent to the backend in
seconds and shown locally with their Minecraft tick equivalent. The built-in
default is 30 seconds.

## Preview Task

`chunkPruneApi.startPreview()` submits one server-level background task and
returns a task id. The request contains the threshold and prune mode only; the
backend scans all dimensions under the server data directory. The shared task
event snapshot and `prune_state` frames provide the latest preview task for each
server, its availability and the latest apply task created after that preview.
There is no periodic `/chunk-prune/state` request. Refreshing
the page or navigating away and back restores the same task state from the
backend without storing task ids in the URL.

Preview progress includes nullable percentages and structured region counters.
Inline settled results populate the shared task cache; excluded large results use
one detail read while retaining the dependent-action guard. Task execution status
remains terminal while its result loads; read failures offer same-task retry.
Both pending and running work display a progress card, disable input changes and
expose cancellation where supported. Pending work is labeled “等待执行”. The page does not
render selected chunks while mcmap is scanning; it waits for a completed task
result before building any preview geometry.

## Overlay Geometry

The geometry endpoint `GET /chunk-prune/previews/{task_id}/geometry` returns a `dimensions` array. Each entry is keyed by `region_dir_relpath` and contains connected shapes, bounds and cell counts. The active map dimension selects one entry
from that array; changing the dimension changes only the displayed preview
slice and does not start a new backend task.

The overlay builder renders the returned rings as one polygon per connected component on a canvas renderer. This keeps large previews from drawing one rectangle per
chunk.

Chunk mode draws chunk-sized cells. Region mode draws region-sized cells. The
overlay is shown only when the completed preview still matches the current
threshold and mode.

## Apply Guard

The destructive apply button is enabled only when:

- preview completed and `state.preview.availability === ready`;
- the current threshold and mode still match the completed preview;
- the server is stopped;
- no apply task is already running.
- a current, valid event snapshot has been received and the stream is connected.

Apply starts a second server-level background task for the completed preview.
The application operation observer refreshes files, world/map metadata and task state after terminal outcomes, including partial failures, even when the page is closed.

## Ownership and preview validity

`features/world/useWorldMapController.ts` owns shared map/dimensions/layers and URL state. `features/world/prune/useChunkPruneController.ts` owns threshold/mode controls, preview/apply confirmation, cancellation and server task projections; the screen renders these controllers.

`state.preview` contains `task_id`, `input_version`, `expires_at`, `availability`, and `apply_task_id`. `preview_task`/`apply_task` are feature-owned projections and remain readable after generic task dismissal. Ready previews can apply only with unchanged controls and a stopped server. Expired/stale/unavailable previews require regeneration; consumed previews cannot apply again, while their available geometry remains useful for inspection. Synchronous 409 details and accepted-task `error_code` values retain inputs and explain how to repreview. Starting or cancelling a task refreshes discovery; closing or navigating away does not send cancel.

Expiry, consumption, stale detection and eviction update streamed availability.
Unknown or disconnected observation blocks new work while retaining task identity.
Accepted IDs cover the interval before domain discovery catches up; observation
does not cancel work when a page closes. Accepted identities and pending requests
are bound to their server, and confirmation rechecks the current connection,
server and preview identity. Backend expiry and stale-input checks remain
authoritative even for a confirmation opened before availability changed.
QueryClient/MSW tests cover unavailable
state, excluded terminal results, dismissal, reconnect and shared late consumers.
Real backend/API evidence covers the actual file and version comparisons.
