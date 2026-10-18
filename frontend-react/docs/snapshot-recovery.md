# Common snapshot and recovery UI

`features/backups` owns shared scope contracts, API/query/command entries, task
observation, previews, history and reusable progress UI. File and world features
compose these public entries. [File operations](file-operations.md) owns path
selection/layout; [world restore](world-restore-page.md) owns map selection and
stopped-world presentation. The backend owns authoritative
[protection](../../backend/docs/snapshots.md) and
[restoration](../../backend/docs/snapshot-restoration.md).

## Snapshot creation and notes

Creation mutations stay pending through the actual task result.
`SnapshotCreateDialog` keeps its closing guard and displays real stages or
available progress. An accepted task ID and 100% progress are not completion.

Notes contain at most 500 Unicode characters. Snapshot lists and source selectors
show the same note; editing changes metadata only. If content creation succeeds
but saving the note fails, retain the created snapshot ID and offer a metadata
retry. Never create another snapshot to repair its note.

## Target feedback and source eligibility

File controls share `GET /snapshots/targets/rules?server_id=...`, bound to the
generation from server details. It returns expanded logical relative exclusions
and a version. The independent rule-query prefix has no timer; page entry,
reconnection, explicit refresh and relevant configuration/writes refresh it.
Unknown, failed or mismatched rules keep protected actions disabled. Selection,
sorting and pagination use local path matching and do not issue per-row POSTs.

`useSnapshotTarget` supports paths and world scopes. `checkWorldTarget` sends
only world scopes to `POST /snapshots/targets/check` for layout/MCA/MCC checks;
it does not send file/project/global scopes or note fields. World selection
feedback and source eligibility are separate from file-rule caching.

Mixed selections skip protected roots; all-protected selections remain disabled.
Sources come from authoritative eligibility results: recorded exclusion is
different from missing coverage. `SnapshotSkipNotice` displays source/preview
`skipped_paths` and `skipped_count`; the browser does not interpret repository
tags or absolute exclusions. Submission retains the original selected scope,
and the backend rechecks current/source/history protection before writing.

## Accepted recovery and observation

`useSnapshotOperation` captures an immutable accepted scope and observes the
task's confirmed terminal result. Execution status and complete result readiness
are separate: a completed task awaiting its result retains busy state and closing
guards. Result-read failures expose an explicit same-task retry in the progress
card or creation status; connection loss is shown separately. Navigation detaches observation without cancelling
the writer. A disappearing active-list entry is not proof of completion; once
discovered, the task ID stays latched until its own outcome is read.

Database-only active restoration discovery works even when repository history
is unavailable and includes global work affecting the selected server. The shared
task event snapshot and `restoration_index` frames contain all active restorations
and their target server identities. File, world and history consumers filter that
same cached index without discovery polling. An absent snapshot, invalid index or
disconnected stream keeps submission blocked; an authoritative empty index permits
new work. Late consumers reuse the current session snapshot and connection.

`FileSnapshotRecovery` owns one file-page recovery session, independent of rows
and pagination. A history dialog owns progress while open so rollback does not
open a second recovery drawer. World recovery can resume after reload even when
its transient map selection is empty.

## Preview lifetime

`useSnapshotPreview` submits the common preparation task and observes real stages.
File actions are paginated by the backend; the world feature supplies map
presentation without a backups dependency on private world modules.

Ready sessions heartbeat every 30 seconds. Missing, conflicting or expired
sessions require regeneration. Closing, replacing or unmounting ready previews
submits cleanup; closing observation during preparation does not cancel work.
The explicit stop action uses task cancellation. Applying a preview carries its
ID so the backend revalidates source, scope, generation, protection and observed
target version before writes. Direct recovery remains available independently.

## History, rollback and cache refresh

History is paginated and filterable by server, scope, outcome and entry point.
Read it on entry, actions and invalidation; do not poll repository history to
observe progress. Terminal results stay visible until dismissed.

Use `rollback_available` and its reason, retained generation/binding information
and feature-specific stopped-state checks to gate rollback. Historical entries
with `binding_issue` stay readable but cannot target a replacement generation.
A rollback replaces later edits in the selected scope and first saves current
state, making another rollback possible. Previously skipped roots stay protected
even if current ignore rules change.

The backups resource registry refreshes snapshots/history after terminal outcomes,
including partial failures and off-page completion. File/world registries handle
their own affected resources. [Operation refresh](operation-refresh.md) owns the
common observer and browser map revisions. Generic task dismissal does not
destroy feature-owned prune preview metadata or retained recovery results.
