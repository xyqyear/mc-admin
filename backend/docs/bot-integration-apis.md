# Bot Integration APIs

mc-admin exposes a small generic API surface for external automation such as
chat bridges. The API is intentionally not bot-specific: consumers own command
parsing, user binding, rate limits, and chat-platform identifiers.

The surface consists of four endpoints:

1. `POST /api/servers/{server_id}/rcon` executes one Minecraft command through
   the server's RCON client and returns the command output.
2. `POST /api/servers/{server_id}/message` renders operator-supplied text in
   game with server-side `tellraw` JSON escaping.
3. `WS /api/events` streams persisted chat and live server/player events, with
   cursor-based chat replay on reconnect.
4. `GET /api/servers/overview` returns every active server, its runtime status,
   and lightweight online-player data in one round trip.

## Authentication

All HTTP endpoints depend on `get_current_user`; the WebSocket endpoint depends
on `get_websocket_user`. A browser session cookie and
`Authorization: Bearer <master_token>` both work for HTTP. Headless WebSocket
clients use the same bearer token and may omit the `Origin` header.

Any authenticated user may call these endpoints. This matches the existing
trust model: ADMIN users already have compose, file, and console access.

The audit middleware logs POST request bodies, so RCON commands and outbound
message bodies are recorded with user context.

## RCON Command

```text
POST /api/servers/{server_id}/rcon
Body: {"command": "whitelist add Notch"}
200:  {"output": "Added Notch to the whitelist"}
```

`app/routers/servers/rcon.py` validates the server exists, checks that it is
healthy, then wraps `MCInstance.send_command_rcon()` in a router-level timeout.
Responses are:

- `404` when the server has no compose file.
- `409` when the server is not healthy enough for RCON.
- `504` when command execution exceeds `RCON_COMMAND_TIMEOUT`.
- `502` when `rcon-cli` exits unsuccessfully after the health check.

The command is passed to `rcon-cli` as one argv element inside the container.
There is no host shell interpolation and no Minecraft-command allowlist in
mc-admin; consumers decide which commands they expose.

## In-Game Message

```text
POST /api/servers/{server_id}/message
Body: {"message": "*<Alice> hello", "target_player": "Notch", "color": "yellow"}
204:  delivered on a best-effort basis
```

`target_player` is optional. When absent, the endpoint sends to `@a`. When
present, it must match `^\w{1,16}$`; selector syntax such as
`@e[type=creeper]` is rejected before any command is sent.

The endpoint splits `message` on newlines and sends one `tellraw` command per
non-empty line. Each JSON component is produced with `json.dumps(...,
ensure_ascii=False)`, which handles quotes, backslashes, control characters,
and CJK text consistently for all consumers.

## Event Stream

```text
WS /api/events?since=<cursor>
Authorization: Bearer <token>
```

Each server-to-client WebSocket message is a JSON object. Chat is the replayable
core event:

```json
{
  "cursor": "184467",
  "type": "chat",
  "server_id": "vanilla",
  "timestamp": "2026-06-12T03:21:00Z",
  "player": {"name": "Notch", "uuid": "069a79f4...", "player_db_id": 7},
  "message": "anyone up for the dragon?"
}
```

Live-only frames include:

```json
{"cursor": null, "type": "player_join", "server_id": "vanilla", "timestamp": "...", "player": {"name": "Notch", "uuid": "069a79f4...", "player_db_id": 7}}
{"cursor": null, "type": "player_leave", "server_id": "vanilla", "timestamp": "...", "player": {"name": "Notch", "uuid": "069a79f4...", "player_db_id": 7}, "reason": "Disconnected"}
{"cursor": null, "type": "server_stopping", "server_id": "vanilla", "timestamp": "..."}
{"type": "heartbeat", "timestamp": "..."}
{"type": "stream_reset", "reason": "cursor_too_old"}
{"type": "stream_reset", "reason": "invalid_cursor"}
```

Clients must ignore unknown `type` values so future event kinds can be added
without breaking older consumers.

### Cursor Semantics

The chat cursor is `player_chat_message.message_id` rendered as a string. Only
chat events carry cursors and only chat is replayable.

`?since=<cursor>` replays persisted chat rows where `message_id > since`, in
ascending primary-key order, then switches to live delivery. Omitting `since`
starts live-only. An invalid cursor sends `stream_reset` with
`reason="invalid_cursor"` and then continues live-only.

The router subscribes to the in-memory event bus before reading replay history.
Events published during replay may appear both in the replay query and the live
queue, so the live drain skips chat frames whose cursor is less than or equal
to the maximum replayed id.

### Event Bus

`app/events/` contains public wire models and the in-process `EventBus`
singleton. It is a fan-out layer for external subscribers only:

```text
LogMonitor._handle_event -> tracking.record_chat_message
                              |
                              | DB commit
                              v
                         event_bus.publish(ChatEvent)
                              |
                              v
                         WS subscribers
```

Each subscription owns a bounded `asyncio.Queue`. Publishing is non-blocking.
If a queue is full, the bus marks that subscription lagged, clears its backlog,
queues a `stream_reset` frame with `reason="cursor_too_old"`, and removes it
from future fan-out. The WebSocket handler sends that frame and closes; the
client reconnects with its last chat cursor.

`record_chat_message()` publishes `ChatEvent` only after the chat row is
committed and has a `message_id`. `process_player_join()`,
`process_player_left()`, and `close_server_sessions()` publish live-only events
after their database side effects complete. The log monitor still calls the
tracking functions directly; no internal subsystem consumes the event bus.

Filtering and identity resolution happen before publication. Ignored player
names are not streamed when they are not persisted, and unresolved online-mode
identities are still dropped by the tracking layer.

## Server Overview

```text
GET /api/servers/overview
200:
[
  {
    "id": "vanilla",
    "name": "vanilla",
    "gamePort": 25565,
    "status": "HEALTHY",
    "online_players": [
      {"name": "Notch", "uuid": "069a79f4...", "player_db_id": 7}
    ]
  }
]
```

The endpoint covers every ACTIVE server row, including stopped servers. It
performs one grouped database query for open player sessions, then reads each
server's compose metadata and runtime status concurrently. Rows whose compose
state has drifted away are skipped with a warning, matching `GET /api/servers/`.

Online players are shown only for statuses at or above `RUNNING`
(`RUNNING`, `STARTING`, `HEALTHY`). Stopped or merely-created servers always
return an empty `online_players` list so stale open sessions do not appear as
live players after crashes.

Online-player data is session-derived, so it has the same staleness envelope as
`GET /api/servers/{server_id}/online-players`.
