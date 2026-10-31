## 1. Ownership isolation

- [x] 1.1 Isolate scheduler wakeup/timer context and cron entry while preserving task cancellation.
- [x] 1.2 Restrict durable outcome projection to the current cron occurrence.
- [x] 1.3 Reject ended nested parents and isolate manager-owned log watchers.

## 2. Business verification

- [x] 2.1 Verify real scheduler, SQLite, Restic and cancellation boundaries with targeted backend regressions.
- [x] 2.2 Verify ended-parent rejection and real log event persistence with targeted tests.
- [x] 2.3 Reproduce the original failure through public APIs, then pass the new deployed scenario in normal and no-reuse modes.
- [x] 2.4 Complete independent review, backend Ruff/Pyright and affected Go checks.

## 3. Documentation and delivery

- [x] 3.1 Update runtime/cron/operation owner docs and API coverage inventory.
- [x] 3.2 Record incident and targeted regression evidence.

## Delivery acceptance

Commit and push the independent branch, then qualify its latest SHA with the
full manual GitHub Actions workflow and `publish=false`. The delivery response
records the immutable SHA, run URL, required gates/audits and conclusion.
Implementation checklist completion does not replace this required acceptance.
