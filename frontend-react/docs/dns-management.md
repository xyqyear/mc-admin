# DNS Management

Page at `/dns` for inspecting and applying DNS changes that keep records and the mc-router routing table in sync with the live server set. Reading the page does not mutate provider state. Clicking “更新记录” applies pending changes through the backend DNS application.

## Layout

Two-column page:

- **Left (2/3 width)**: DNS records table — current state from the configured provider
- **Right (1/3 width)**: mc-router routes table — current routes the router knows about

`DNSStatusResponse` retains initialized/dns_diff/router_diff and accepts additive state/known flags, unknown_servers, issues and empty_desired. Older responses remain readable, with null comparisons marked unconfirmed. A status badge in the top-right shows aggregate health:

- 🟢 normal (records and routes match desired state)
- 🟡 pending changes (diff is non-empty), pending initialization, or incomplete comparison
- 🔴 error (provider call failed, credentials missing, etc.)
- ⚪ disabled (`dynamic_config.dns.enabled === false`)

## Conditional states

The page renders different shells depending on what the backend reports:

- **Disabled** → alert with "Go to settings" button (links to `/config?module=dns`).
- **Not initialized** → alert with explanation and the same settings link. Happens when the provider hasn't been configured yet.
- **Pending changes** → diff display above the tables: add list (green), update list (yellow), remove list (red). Each entry shows record key + values.
- **Healthy** → just the tables, only after both provider comparisons are known.
- **Degraded** → safe `issues` and `unknown_servers` stay visible; a null diff never implies synchronized state. The readable provider side still displays its actual changes.
- **Empty desired configuration** → explicitly says existing records/routes are being retained.

## Buttons

- **Refresh** — re-fetches status, records, routes and enabled state; failures produce an error rather than a success toast
- **Update** — POST `/api/dns/update`; refreshes status/records/routes after either success or failure, because a failed overall request may have already updated the healthy provider
- **Settings** — link to dynamic config

The page applies changes through its Update action. Server creation, removal and filesystem synchronization also ask the backend DNS manager to reconcile when `dynamic_config.dns.enabled` is true. There is no separate `auto_update` setting. Disabling DNS makes later lifecycle updates no-ops; the manager releases its old router client and does not write through stale provider clients.

## Tables

20-row pagination, truncated cells with title-attribute tooltips. DNS columns:

- 子域名 (subdomain)
- 记录类型 (type)
- 值 (value)
- TTL
- 记录ID (provider's internal id)

Routes columns: server address → forwarded host:port.

## Data sources

| Query                  | Endpoint                | Cadence   |
| ---------------------- | ----------------------- | --------- |
| `dns.enabled()`        | `GET /api/dns/enabled`  | manual    |
| `dns.status()`         | `GET /api/dns/status`   | 60 seconds |
| `dns.records()`        | `GET /api/dns/records`  | 10 seconds |
| `dns.routes()`         | `GET /api/dns/routes`   | 10 seconds |
| `useUpdateDns()`       | `POST /api/dns/update`  | mutation  |

Queries poll while enabled and also support explicit refresh. The tables paginate the records returned by the provider; page navigation does not fetch additional provider-side pages.

## Files

- `features/dns/DnsManagementScreen.tsx`
- `features/dns/api.ts`, `features/dns/queries.ts`, `features/dns/commands.ts`
