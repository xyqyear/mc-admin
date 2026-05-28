# Log Monitor (`app.log_monitor`)

Watches each running server's `logs/latest.log` and dispatches parsed events to the player tracking layer in real time.

## Why this layer exists

Modern Minecraft has no first-class API for "tell me when a player joins" — the canonical signal is a regex match in the log file. RCON `list` gives a snapshot but misses join/leave timing, chat messages, and achievements. Tailing `latest.log` is how every server-management tool gets these signals.

## Implementation

- **File watching**: `watchfiles` (Rust-backed, kernel inotify on Linux) per server. The monitor stores a byte offset; on file change, it reads only new bytes from that offset, handling rotation by detecting truncation.
- **Parsing** (`parser.py`): each new line runs through an ordered regex chain — UUID-discovered → join → leave → chat → achievement → server-stop. First match wins. Patterns live in `dynamic_config.log_parser` so an admin can adapt them per modpack without redeploying.
- **Dispatch** (`monitor.py`): each parsed event maps to one tracking function:

| Event                          | Calls                                              |
| ------------------------------ | -------------------------------------------------- |
| `PlayerUuidDiscoveredEvent`    | `upsert_player()` (records v4 UUIDs immediately)   |
| `PlayerJoinedEvent`            | `process_player_join()`                            |
| `PlayerLeftEvent`              | `process_player_left()`                            |
| `PlayerChatMessageEvent`       | `record_chat_message()`                            |
| `PlayerAchievementEvent`       | `record_achievement()`                             |
| `ServerStoppingEvent`          | `close_server_sessions()`                          |

## Public surface

```python
from app.log_monitor import log_monitor

await log_monitor.start_server(server_id)   # begins watching latest.log
await log_monitor.stop_server(server_id)
await log_monitor.stop_all()                # called on shutdown
```

The singleton is started from `start_player_system()` (one watcher per active server), stopped from `stop_player_system()` after `player_syncer` so we don't lose late events during shutdown.

## Files

- `monitor.py` — `LogMonitor` singleton: per-server tail loop, file rotation handling, dispatch.
- `parser.py` — `LogParser`: regex compilation + ordered match.
- `events.py` — Pydantic event models; one per detected log line type.

## Configuration

`dynamic_config.log_parser`: `uuid_patterns`, `join_pattern`, `leave_pattern`, `chat_pattern`, `achievement_patterns`, `server_stop_pattern`. Updated at runtime through the dynamic-config UI; the monitor recompiles on change.
