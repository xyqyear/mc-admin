# Log Monitor (`app.log_monitor`)

Watches each active server's `logs/latest.log` and dispatches parsed events to the player tracking layer in real time.

## Why this layer exists

Modern Minecraft has no first-class API for "tell me when a player joins" — the canonical signal is a regex match in the log file. RCON `list` gives a snapshot but misses join/leave timing, chat messages, and achievements. Tailing `latest.log` is how every server-management tool gets these signals.

## Implementation

- **File watching**: `watchfiles` per server uses kernel notifications where available and automatically selects polling on WSL. The monitor stores a byte offset and reads only new bytes, handling creation events and truncation during rotation. Idle watcher timeouts reconcile file size and unread content every second: polling notifications can miss writes that share the same whole-second mtime, so notifications alone cannot guarantee delivery of the final log lines.
- **Parsing** (`parser.py`): each new line runs through an ordered regex chain — UUID-discovered → join → leave → chat → achievement → server-stop. First match wins. Patterns live in `dynamic_config.log_parser` so an admin can adapt them per modpack without redeploying.
- **Dispatch** (`monitor.py`): each parsed event calls the runtime player service. The monitor never accesses
  player storage or opens database sessions:

| Event                          | Calls                                              |
| ------------------------------ | -------------------------------------------------- |
| `PlayerUuidDiscoveredEvent`    | `PlayerService.discover_identity()` (records v4 UUIDs immediately)   |
| `PlayerJoinedEvent`            | `process_player_join()`                            |
| `PlayerLeftEvent`              | `process_player_left()`                            |
| `PlayerChatMessageEvent`       | `record_chat_message()`                            |
| `PlayerAchievementEvent`       | `record_achievement()`                             |
| `ServerStoppingEvent`          | `close_server_sessions()`                          |

## Public surface

```python
from app.log_monitor import get_log_monitor

log_monitor = get_log_monitor()

await log_monitor.start_server(server_id)   # begins watching latest.log
await log_monitor.stop_watching(server_id)
await log_monitor.stop_all()                # called on shutdown
```

The runtime-owned monitor is started from `start_player_system()` (one watcher per active server), stopped from `stop_player_system()` after `player_syncer` so we don't lose late events during shutdown.

## Files

- `monitor.py` — `LogMonitor`: per-server tail loop, file rotation handling, dispatch.
- `parser.py` — `LogParser`: regex compilation + ordered match.
- `events.py` — Pydantic event models; one per detected log line type.

## Configuration

`dynamic_config.log_parser`: `uuid_patterns`, `join_pattern`, `leave_pattern`, `chat_pattern`, `achievement_patterns`, `server_stop_pattern`. Updated at runtime through the dynamic-config UI; the monitor recompiles on change.

## Observation and history boundaries

`LogMonitor(players=...)` accepts an explicit player service. Without one, it
resolves `get_player_service()` for the active runtime. UUID discovery, joins,
chat, achievements, departures and server-stop observations therefore use the
same identity/session rules as RCON and heartbeat recovery.

The initial tail position is the existing file's end; historical log lines are
not replayed on startup. A newly created or truncated file is read from its
beginning. Byte positions and ordered line processing remain local to each
watcher. Public chat history uses committed database message IDs as cursors, not
file offsets. The service publishes each wire event after its database side
effects have committed, and schedules a join's skin fetch after publication.
