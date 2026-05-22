# Player Management

Surface for everything the backend's player-tracking system records: who's been on a server, when, what they said, what they earned. Two views: the global Player Management page (table across all servers) and the server-overview's online-players card.

## Pages and components

- `pages/PlayerManagement.tsx` — global page at `/players`. Sortable, filterable table of every recorded player.
- `components/players/PlayerFilters.tsx` — search box (name / UUID substring), online-only toggle, server dropdown. Filters cascade into `usePlayerQueries({ online_only, server_id })`.
- `components/players/PlayerDetailDialog.tsx` — detail dialog with four tabs:
  - **基本信息** — UUID (formatted `8-4-4-4-12`), current name, first seen, last seen, total playtime
  - **会话记录** — `PlayerSession` rows with join/leave timestamps and computed durations
  - **聊天记录** — `PlayerChatMessage` history with timestamps
  - **成就记录** — `PlayerAchievement` list scoped per server
- `components/players/MCAvatar.tsx` — renders the 8×8 avatar PNG the backend mirrored from Mojang. Falls back to a deterministic placeholder when missing.
- `components/server/OnlinePlayersCard.tsx` — server-overview card listing currently-online players. Polls `players.serverOnline(serverId)` every 10 s, gated on `status === HEALTHY`.

## Data sources

| Query                                      | Endpoint                                  | Cadence                |
| ------------------------------------------ | ----------------------------------------- | ---------------------- |
| `players.list(filters)`                    | `GET /api/players/`                       | manual / on filter     |
| `players.detailByUUID(uuid)`               | `GET /api/players/uuid/{uuid}`            | manual                 |
| `players.sessions(playerDbId, params)`     | `GET /api/players/{id}/sessions`          | manual                 |
| `players.chat(playerDbId, params)`         | `GET /api/players/{id}/chat`              | manual                 |
| `players.achievements(playerDbId, srvId)`  | `GET /api/players/{id}/achievements`      | manual                 |
| `players.serverOnline(serverId)`           | `GET /api/servers/{id}/online-players`    | 10 s, HEALTHY-gated    |
| `players.sessionStats(playerDbId, period)` | `GET /api/players/{id}/sessions/stats`    | manual                 |

The drawer drives 4–5 of these in parallel when opened; React Query dedupes identical keys so navigating between tabs doesn't refetch already-loaded data.

## UUID formatting

Mojang returns hex without dashes (`8667ba71b85a4004af54457a9734eed7`); our backend stores the same shape. The frontend's `formatUUID` helper (`utils/formatUtils.ts`) renders it as `8667ba71-b85a-4004-af54-457a9734eed7` for display and back to compact for API calls.

## Where the data comes from

The backend's `app.players` system writes to `Player`, `PlayerSession`, `PlayerChatMessage`, `PlayerAchievement` tables driven by:

- Real-time log parsing (LogMonitor → tracking functions)
- RCON sync every N seconds (PlayerSyncer reconciles drift)
- Heartbeat-driven crash recovery (closes orphan sessions on restart)

The frontend doesn't interact with any of that machinery — it just reads the resulting tables.
