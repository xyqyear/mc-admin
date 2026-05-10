# Player Tracking (`app.players`)

Tracks who's online, when they joined and left, what they said in chat, and what achievements they earned. Skin avatars are mirrored locally so the frontend doesn't have to call Mojang from the browser.

## Direct function calls, not events

There is no event dispatcher. Producers (LogMonitor, HeartbeatManager, PlayerSyncer, REST handlers) call composite functions in `app/players/tracking.py` directly. The composites handle "ensure player exists in DB" + the side effect:

- `process_player_join(server_id, player_name, timestamp)` — `get_or_add_player_by_name` (calls Mojang for the UUID if missing), open a `PlayerSession`, schedule a skin update task.
- `process_player_left(server_id, player_name, reason, timestamp)` — close every open session for that (player, server).
- `record_chat_message(server_id, player_name, message, timestamp)` — upsert player + insert `PlayerChatMessage`.
- `record_achievement(server_id, player_name, achievement_name, timestamp)` — match the in-game name against known players (longest-first to avoid prefix collisions), insert `PlayerAchievement` (unique on `(player, server, achievement)`).
- `close_server_sessions(server_id, timestamp)` — close every open session on that server (called when the server stops).
- `update_player_skin(player_db_id, uuid, player_name)` — fetch skin via `skin_fetcher`, write `Player.skin_data` and `Player.avatar_data`.

## Singletons

Each owns its own lifecycle and runs as a background task.

- **`heartbeat_manager`** (`app.players.heartbeat`) — single-row `SystemHeartbeat` table, updated every `heartbeat_interval_seconds`. On startup, if `now - last_heartbeat >= crash_threshold_minutes`, treats it as a crash: closes every open session via `process_player_left()` (with a "crash" reason and the last-heartbeat timestamp) and calls `player_syncer.validate_all_servers()` to resync against RCON.
- **`player_syncer`** (`app.players.player_syncer`) — periodic loop. For each `HEALTHY` server, runs RCON `list` and reconciles the result against open `PlayerSession` rows: false-online → `process_player_left`, false-offline → `process_player_join`.
- **`skin_fetcher`** (`app.players.skin_fetcher`) — Mojang client. Hits `https://sessionserver.mojang.com/session/minecraft/profile/{uuid}`, decodes the textures property, downloads the SKIN PNG, and crops the 8×8 head into an avatar via `async_fs.extract_skin_avatar` (PIL, run off the loop). Rate-limited, handles 404/429/timeout.

## Lifecycle wiring

`start_player_system()` and `stop_player_system()` in `app/players/__init__.py` are called from `app.main` lifespan. Order matters because `heartbeat_manager.start()` runs the crash check before anything else inspects DB state:

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

- **`Player`** — `uuid` (unique), `current_name`, `skin_data` (bytes), `avatar_data` (bytes), `last_skin_update`, `created_at`.
- **`PlayerSession`** — `(player_db_id, server_db_id)`, `joined_at`, `left_at` (nullable), `duration_seconds` (nullable). Indexes on `(player, time)`, `(server, time)`, and the open-session shape.
- **`PlayerChatMessage`** — `(player_db_id, server_db_id)`, `message_text`, `sent_at`. Indexes on `(player, time)` and `(server, time)`.
- **`PlayerAchievement`** — `(player_db_id, server_db_id, achievement_name)` unique, `earned_at`.
- **`SystemHeartbeat`** — single-row crash detector.

All timestamps are `TZDatetime` (UTC-aware; naive values rejected at the model layer).
