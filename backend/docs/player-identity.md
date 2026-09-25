# Player Identity Resolution

`app.players.identity_resolver` resolves Minecraft names and UUIDs while keeping
offline-mode identities out of the player database.

## Sources

The resolver reads `usercache.json` from the server data directory:

```text
get_docker_mc_manager().get_instance(server_id).get_data_path() / "usercache.json"
```

Entries are keyed by lowercase player name and normalized dashless UUID. Only
UUID version 4 entries are accepted. Version 3 UUIDs are offline-mode identities
and are treated as invalid for player storage and processing.

If a requested name or UUID is present in `usercache.json` only with a non-v4
UUID, resolution fails immediately and does not call Mojang. If the cache entry
is absent, the resolver falls back to Mojang:

- name -> UUID: `https://api.mojang.com/users/profiles/minecraft/{name}`
- UUID -> name: `https://sessionserver.mojang.com/session/minecraft/profile/{uuid}`

## Database Gates

`PlayerService` owns UUID discovery and name-only observations from logs, RCON
and crash recovery. Its name-only writes go through
`PlayerService.ensure_player(session, server_id, player_name)`. Existing database
rows are reused only when their stored UUID is v4. Missing names resolve through
`usercache.json` first, then Mojang, and are inserted only after a v4 UUID is
available. Names matching `players.ignored_name_prefixes` are skipped before
identity resolution. The default ignored prefix list is `["bot_"]`.

UUID-known writes also require v4 UUIDs:

- `upsert_player()` skips non-v4 UUIDs from log discovery.
- `upsert_player_profile()` skips non-v4 UUIDs from profile caching.
- `get_player_by_uuid()` returns `None` for non-v4 UUIDs.
- `update_player_skin()` skips Mojang skin fetches for non-v4 UUIDs.

`upsert_player()` and `upsert_player_profile()` also skip names matching
`players.ignored_name_prefixes` with case-insensitive prefix comparison.

The map profile endpoint keeps its own lightweight gate: syntactically valid
non-v4 UUIDs return an unresolved response without cache or Mojang lookups.

## Service and adapter ownership

`PlayerService` is constructed once per runtime with explicit persistence, event,
skin-client and background-task dependencies. `get_player_service()` returns that
instance; a producer can receive it directly for an isolated test or application.
The service injects the usercache/Mojang name resolver as its external identity
adapter and captures its own runtime configuration for ignored-name checks.
Calling an explicit service from another bound runtime still uses the service
owner's usercache, configuration, database, clients and event publisher. CRUD
functions perform no network identity lookup. The storage layer retains the v4
and ignored-prefix gates for both tracking and profile cache writes. Consolidation does not change source priority or turn an invalid
usercache identity into a Mojang fallback.

Skin fetching follows committed join publication and uses the owning runtime's
client and task lifecycle. Fetch failure does not undo a joined session or its
public event. Profile responses and historical chat cursors keep their existing
wire contracts.
