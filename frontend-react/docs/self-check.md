# Self-Check Dashboard

The protected root route (`/`) renders `src/pages/SelfCheck.tsx`. It is an
operational dashboard, not a landing page.

## Data Flow

Raw API calls and response types live in `hooks/api/selfCheckApi.ts`.

Query hooks:

- `useSelfCheckStatus()` polls `/api/self-check/status` for the catalog,
  current health state, and recent retained run summaries.
- `useSelfCheckRun(runId)` loads retained findings for a selected run.
- `useSelfCheckCatalog()` and `useSelfCheckRuns()` are available for narrower
  consumers.
- `useSelfCheckHealth()` derives unresolved warning and critical counts from
  the current health state for global indicators.

Manual full runs use `useEventStream()` against `/api/self-check/run/stream` so
findings appear as each check completes. Single-card reruns use
`useSelfCheckMutations().useRunSelfCheckItem()`. Completed runs invalidate
`queryKeys.selfCheck.all`.

## Page Behavior

The dashboard shows:

- summary counts for the displayed run
- manual run button
- every finding from the current health state, live stream, or selected history run
- per-card rerun controls
- retained run history

Healthy and unhealthy runs are retained for the configured retention window, and
retained details include every finding.

Single-card reruns update the displayed card immediately and invalidate
self-check queries. After refresh, `/api/self-check/status` derives the same
current state from the latest full run plus later single-check reruns, filtered
to checks that are currently enabled.

Selecting a retained run switches the result panel to that historical result.
The result header offers a return action that clears the selected history run
and displays the current health state again.

## Navigation

The sidebar labels `/` as `系统自检`. Submenus stay collapsed on the root route.
If the current health state has unresolved warning or critical findings, the
sidebar item shows a badge and the main layout shows a global alert strip.

## Cron UI Coupling

`self_check` is registered as a backend system cron job. Cron API types include
`is_system` and registration defaults. The cron management page:

- displays a `System` badge for system jobs
- hides pause/resume/cancel controls for system jobs
- keeps task type locked in edit mode
- allows editing name, cron expression, seconds field, and params
