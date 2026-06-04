# Player Locations

`app.player_locations` extracts last-saved player positions from the primary
world root with `mcmap --json extract-players --world <world>`. The feature is
used by the world-restore map and is intentionally independent from Mojang
availability: location extraction returns UUIDs, dimension ids, canonical
region-directory relpaths, and skipped player files without waiting for profile
lookups.

## API Surface

- `GET /servers/{server_id}/world-restore/player-locations`
  returns `PlayerLocationsResponse`.
- `GET /players/uuid/{uuid}/profile` returns a lightweight map profile for one
  UUID. Dashed and dashless UUIDs are normalized to the dashless lowercase DB
  form. Syntactically valid non-v4 UUIDs return `resolved = false`.
- `POST /players/profiles/stream` accepts `{ "uuids": [...] }` and streams SSE
  events for bulk map-profile resolution. Cached rows are emitted first, then
  uncached online UUIDs are resolved through Mojang with bounded network
  concurrency.

The location response includes:

- `dimensions[]` from mcmap, with `folder` resolved against the primary world
  root path to `region_dir_relpath` under the server data directory.
- `players[]` with `id`, `id_kind`, optional normalized `uuid`, storage kind,
  dimension id, optional `region_dir_relpath`, and block position.
- `skipped[]` for malformed or incomplete files reported by mcmap. Skips are
  non-fatal because a single bad player file should not hide valid locations.

## Extraction

`player_locations.runner.extract_players()` wraps the mcmap subprocess in the
same `MCMapProcess` NDJSON reader used by the map and FTB claims pipelines. The
reader validates `result.data` with command-specific Pydantic payload models
before extraction code builds API response objects. When running as root, it
passes `--chown <uid>:<gid>` derived from the server data directory so generated
or touched files keep host ownership.

`extract_player_locations_for_server(data_path, world_root)` uses the primary
world root, matching the FTB claims overlay. Dimension folders are resolved by
safely joining the world root with the mcmap folder and `region/`; absolute and
parent-traversal folders are rejected. A folder gets `region_dir_relpath` only
when that specific region directory contains at least one valid MCA file.
Unknown or absent dimensions stay in the response with
`region_dir_relpath = null`.

## Profile Cache

The single-profile endpoint first rejects non-v4 UUIDs with an unresolved
response. It then reads the existing `Player` table by normalized UUID. A cached
player with avatar data is returned immediately. Missing or incomplete cache
entries call Mojang's session server for name and texture data, extract the 8x8
avatar from the skin image, and upsert the `Player` row.

Mojang 404, 429, timeout, malformed texture payloads, or skin download failures
return a 200 response with either the cached DB identity or an unresolved
profile.

The bulk stream uses the same normalization and cache semantics, but it performs
one cache scan for the requested UUID set and opens short-lived database
sessions only for cache reads and individual upserts. Mojang fetches run outside
database sessions, with bounded concurrency, so a dimension containing hundreds
of player files does not create hundreds of browser requests or hold SQLite
transactions while network I/O is pending. The frontend can therefore render
locations first and let names and avatars appear as streamed profile events
arrive.
