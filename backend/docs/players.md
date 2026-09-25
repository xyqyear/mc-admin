# Player Tracking (`app.players`)

Tracks who's online, when they joined and left, what they said in chat, and what achievements they earned. Skin avatars are mirrored locally so the frontend doesn't have to call Mojang from the browser.

## Player application service

`get_player_service()` returns the current runtime's `PlayerService`. The runtime
constructs it with its database session factory, public event publisher, owned
skin-task spawner, skin client and clock. Producers can receive the same service
explicitly; they do not write identity or session rows themselves.

- `LogMonitor` parses log lines and calls `discover_identity`,
  `process_player_join`, `process_player_left`, `record_chat_message`,
  `record_achievement` or `close_server_sessions` in line order.
- `PlayerSyncer` obtains a `HEALTHY` server's RCON `list` result and calls
  `reconcile_online`. The service compares it with open sessions, closes false
  online observations, then opens missing sessions. A failed RCON request is an
  unknown observation and makes no session changes.
- `HeartbeatManager` detects a stale heartbeat and calls `recover_crash` with
  the last heartbeat timestamp. The service closes open sessions before the
  manager triggers RCON reconciliation.
- The skin refresh endpoint calls `update_player_skin` through the same service.

Each action obtains its own database session. Reconciliation and crash recovery
finish their read session before invoking write actions, so concurrent producers
do not share an `AsyncSession` or keep read transactions open across external
identity lookups. Join, chat and identity discovery share the v4 UUID and dynamic
ignored-name gates in the player storage layer. Achievements match known v4 names
longest-first and retain uniqueness on `(player, server, achievement)`.

The external subscriber event bus in `app/events` is the only exception to the
no-dispatcher rule. Service actions publish public wire events after their
database side effects complete; chat is published only after the
`PlayerChatMessage` row is committed and its `message_id` cursor is assigned.
Join publication precedes the owned skin update task. Duplicate observations keep
the existing public join/leave notifications while reusing or conditionally
closing the canonical session. Internal code does not consume the event bus. SQLite allocates chat IDs with explicit
AUTOINCREMENT, so cleanup does not reuse a previously committed cursor even when
it removes the highest message or empties the table. Startup migration preserves
existing rows and indexes; its allocation baseline is the highest retained ID.
Identifiers already deleted before this migration cannot be reconstructed, so
non-reuse relative to that lost historical high-water mark is not guaranteed.

Identity resolution and UUID validity rules are documented in
`docs/player-identity.md`. Player storage and skin/profile fetches accept only
online-mode UUIDs. Dynamic `players.ignored_name_prefixes` excludes matching
names from write-side tracking and profile-cache creation using
case-insensitive prefix matching. Its default is `["bot_"]`.

`app.players.crud.player_cleanup` exposes maintenance helpers for stored rows
that predate those gates. Cleanup previews list all matching players and their
related session/chat/achievement counts. Cleanup deletes recompute the current
candidate set before removing player rows and dependent records.

Player session, chat and achievement history queries apply an optional server
filter to every returned row. An unknown server yields an empty list; omitting
the filter returns that player's history across servers.

## Runtime resources

Each application owns its producers and external clients. Background producers
are stopped and drained before database and client teardown.

- **`heartbeat_manager`** (`app.players.heartbeat`) — single-row `SystemHeartbeat` table, updated every `heartbeat_interval_seconds`. On startup, if `now - last_heartbeat >= crash_threshold_minutes`, treats it as a crash: calls `PlayerService.recover_crash()` to close open sessions with the "System crash" reason and last-heartbeat timestamp and calls `player_syncer.validate_all_servers()` to resync against RCON.
- **`player_syncer`** (`app.players.player_syncer`) — periodic loop. For each `HEALTHY` server, runs RCON `list` and passes the observation to `PlayerService.reconcile_online`. The service owns comparison and session changes.
- **`skin_fetcher`** (`app.players.skin_fetcher`) — Mojang client. Hits `https://sessionserver.mojang.com/session/minecraft/profile/{uuid}`, decodes the textures property, downloads the SKIN PNG, and crops the 8×8 head into an avatar via `async_fs.extract_skin_avatar` (PIL, run off the loop). Handles 404/429/timeout.

## Lifecycle wiring

`start_player_system()` and `stop_player_system()` in `app/players/__init__.py` are composed by the application runtime. Order matters because `heartbeat_manager.start()` runs the crash check before anything else inspects DB state:

```text
start_player_system():
    heartbeat_manager.start()        # crash check → recovery → tick loop
    log_monitor.start_server(id)     # for each active server
    player_syncer.start()            # validation loop

stop_player_system():
    player_syncer.stop()
    log_monitor.stop_all()
    heartbeat_manager.stop()
```

## Database models

Persistent models live in `app.players.models`; the aggregate Alembic metadata
registers them explicitly. Map-profile request and response payloads live in
`app.players.api_models`, while query projections stay with their player queries.

- **`Player`** — `uuid` (unique), `current_name`, `skin_data` (bytes), `avatar_data` (bytes), `last_skin_update`, `created_at`.
- **`PlayerSession`** — `(player_db_id, server_db_id)`, `joined_at`, `left_at` (nullable), `duration_seconds` (nullable). Ending a session clamps `left_at` to at least `joined_at`, so a crash heartbeat preceding a recent join contributes zero seconds. Both individual-player departures and server-wide closure use this rule. Indexes on `(player, time)`, `(server, time)`, and the open-session shape.

The SQLite partial unique index `uq_player_session_open` permits at most one
open session per player/server pair. Join handling uses an atomic SQLite insert
with conflict handling, then reads the canonical open row before committing.
Concurrent log and RCON observations reuse its identity. Departure updates only
rows that remain open, so a repeated or concurrent departure cannot replace an
already recorded duration. Closed sessions and sessions on other servers remain
independent. Historical duplicate open sessions require the explicitly reviewed
offline repair described in `database-migrations.md`; startup does not silently
rewrite player history.
- **`PlayerChatMessage`** — `message_id` cursor, `(player_db_id, server_db_id)`, `message_text`, `sent_at`. Indexes on `(player, time)` and `(server, time)`.
- **`PlayerAchievement`** — `(player_db_id, server_db_id, achievement_name)` unique, `earned_at`.
- **`SystemHeartbeat`** — single-row crash detector.

All timestamps are `TZDatetime` (UTC-aware; naive values rejected at the model layer).
