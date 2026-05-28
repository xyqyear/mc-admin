# Player Identity Resolution

`app.players.identity_resolver` resolves Minecraft names and UUIDs while keeping
offline-mode identities out of the player database.

## Sources

The resolver reads `usercache.json` from the server data directory:

```text
docker_mc_manager.get_instance(server_id).get_data_path() / "usercache.json"
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

Name-only tracking calls go through
`get_or_add_player_by_name(session, server_id, player_name)`. Existing database
rows are reused only when their stored UUID is v4. Missing names resolve through
`usercache.json` first, then Mojang, and are inserted only after a v4 UUID is
available.

UUID-known writes also require v4 UUIDs:

- `upsert_player()` skips non-v4 UUIDs from log discovery.
- `upsert_player_profile()` skips non-v4 UUIDs from profile caching.
- `get_player_by_uuid()` returns `None` for non-v4 UUIDs.
- `update_player_skin()` skips Mojang skin fetches for non-v4 UUIDs.

The map profile endpoint keeps its own lightweight gate: syntactically valid
non-v4 UUIDs return an unresolved response without cache or Mojang lookups.
