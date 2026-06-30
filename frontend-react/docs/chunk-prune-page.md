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
backend scans all dimensions under the server data directory. The page stores
that id in the hash URL as `task`, so a reload polls the same task again
through the shared task query hook.

Preview progress is the generic background task progress. The page does not
render selected chunks while mcmap is scanning; it waits for a completed task
result before building any preview geometry.

## Overlay Geometry

The completed preview task result carries a `dimensions` array. Each entry is
keyed by `region_dir_relpath` and contains `selected_chunks` in chunk mode or
`selected_regions` in region mode. The active map dimension selects one entry
from that array; changing the dimension changes only the displayed preview
slice and does not start a new backend task.

The overlay builder turns connected cells into boundary rings with
`computeBoundaryRings`, then renders one polygon per connected component on a
canvas renderer. This keeps large previews from drawing one rectangle per
chunk.

Chunk mode draws chunk-sized cells. Region mode draws region-sized cells. The
overlay is shown only when the completed preview still matches the current
threshold and mode.

## Apply Guard

The destructive apply button is enabled only when:

- preview completed;
- the current threshold and mode still match the completed preview;
- the server is stopped;
- no apply task is already running.

Apply starts a second server-level background task for the completed preview.
On completion the page invalidates task and map query keys so stale map tiles
are refetched.
