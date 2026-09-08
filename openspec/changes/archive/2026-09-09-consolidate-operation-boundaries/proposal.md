## Why

Normal administration journeys cross inconsistent configuration, maintenance, and upload boundaries: stopped servers cannot rebuild, previews may use a different template from saves, and completed tasks can precede required metadata. Consolidate the owners of those operations while correcting the practical defects identified by the design review.

## What Changes

- Make configuration preparation, preview, application, metadata and task completion consistent while preserving template snapshots, explicit upgrades, conversions and running intent.
- Give destructive world maintenance shared server availability and reliable cancellation/history cleanup; restore missing sidecar directories and keep ordinary file restores available online.
- Consolidate each frontend upload flow's own lifetime and batch policy; revoke deleted-user sessions, tolerate disappearing directory entries and give compression outputs independent identities.
- Validate editable template/log rules at their definition boundary, honor DNS hot disable and finish each DNS update before releasing its ownership.
- Keep chat replay cursors monotonic across cleanup and bound crash-recovery playtime at zero.
- Separate E2E reservation, deployment, stream and diagnostic/cleanup budgets; extend focused behavioral coverage.
- Non-goals: arbitrary concurrency guarantees, persistent workflow/upload platforms, general DNS management, exhaustive special-path support, adversarial report/manifest hardening and automatic cross-system rollback.

## Capabilities

### New Capabilities

- `operation-consistency`: Observable completion, ownership and compatibility contracts for existing administration operations and their verification.

### Modified Capabilities

None. Existing game-port and Cron weekday requirements remain unchanged.

## Impact

Backend services, selected HTTP/SSE routes, React operation flows, pytest, the standalone E2E runner and domain cases. A server-snapshot preview endpoint and maintenance visibility are additive. A SQLite migration preserves chat rows while preventing future identifier reuse. No intentional breaking API/configuration changes; invalid newly submitted rule definitions receive validation errors, and deleted identities lose access. Docker deployment remains a single application image with the existing real test fixtures.
