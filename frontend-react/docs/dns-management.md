# DNS Management

Page at `/dns` for inspecting and applying DNS changes that keep records and the mc-router routing table in sync with the live server set. The page is read-only on its own — clicking "Update" applies pending changes via `SimpleDNSManager.update()` on the backend.

## Layout

Two-column page:

- **Left (2/3 width)**: DNS records table — current state from the configured provider
- **Right (1/3 width)**: mc-router routes table — current routes the router knows about

A status badge in the top-right shows aggregate health:

- 🟢 normal (records and routes match desired state)
- 🟡 pending changes (diff is non-empty)
- 🔴 error (provider call failed, credentials missing, etc.)
- ⚪ disabled (`dynamic_config.dns.enabled === false`)

## Conditional states

The page renders different shells depending on what the backend reports:

- **Disabled** → alert with "Go to settings" button (links to `/dynamic-config`).
- **Not initialized** → alert with explanation and the same settings link. Happens when the provider hasn't been configured yet.
- **Pending changes** → diff display above the tables: add list (green), update list (yellow), remove list (red). Each entry shows record key + values.
- **Healthy** → just the tables.

## Buttons

- **Refresh** — re-fetches `dns.records()` and `dns.routes()`
- **Update** — POST `/api/dns/update` (mutation), invalidates `dns.all` on success
- **Settings** — link to dynamic config

The update flow is intentionally manual: applying DNS changes can take seconds and may flap a live game. Auto-update is opt-in via `dynamic_config.dns.auto_update`.

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
| `dns.status()`         | `GET /api/dns/status`   | manual    |
| `dns.records()`        | `GET /api/dns/records`  | manual    |
| `dns.routes()`         | `GET /api/dns/routes`   | manual    |
| `useUpdateDns()`       | `POST /api/dns/update`  | mutation  |

All polling is manual — DNS state doesn't change behind our back, so an admin clicking Refresh is the right trigger.

## Files

- `pages/DnsManagement.tsx`
- `hooks/api/dnsApi.ts`, `hooks/queries/base/useDnsQueries.ts`, `hooks/mutations/useDnsMutations.ts`
