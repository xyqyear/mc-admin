# Operation completion and cache refresh

This page owns application-level refresh after committed backend changes.
[Data architecture](data-architecture.md) owns query keys and dependency direction;
[task center](task-center.md) owns progress/results. The
[backend feed contract](../../backend/docs/operations.md#incremental-cache-refresh)
defines cursors and reset behavior; the behavioral source is
[operation refresh sync](../../openspec/specs/operation-refresh-sync/spec.md).

## Discovery and terminal changes

Feature commands wake operation discovery when background work is accepted and when synchronous journaled writes settle, including possible partial failures. File write/create/rename, completed or partially written ordinary uploads, archive rename/compression and task cancellation use their owning command/controller boundary. Preview and self-check acceptance wake discovery before any view-local observation guard, so leaving during submission does not defer global observation. `waitForTaskResult` wakes on acceptance and observation end for its task consumers. Read-only checks, searches and upload conflict/policy reads do not wake operation discovery.

`app/operations/OperationObserver.tsx` is mounted once within the authenticated layout. It subscribes to `operation_changes` frames on the shared task event connection. Batches contain up to 200 lightweight notifications from the runtime-owned bounded memory feed; no periodic `/operations/changes` request runs. Instance-scoped opaque cursors recover across navigation and network reconnect; historical operation list/detail reads remain independent. Cron keeps its own observation behavior, while its existing operation effects still refresh through this shared feed.

Features register affected keys through `operationResources.ts`; configuration, servers, files/archives, world, backups/history, health and DNS declare their own operations. Each received terminal change updates map revisions and merges the affected query keys for one invalidation per batch. Success, failure, cancellation, interruption and skipped outcomes synchronize the corresponding business resources even after the initiating page or progress dialog closes. A later effective change of the same operation can invalidate again; operation IDs do not suppress newer notifications.

The observer cancels affected in-flight reads, marks their resources stale and processes each batch before advancing a session-scoped Query checkpoint. The transport awaits this callback before consuming another batch and reconnects with the last acknowledged cursor. Cancellation includes initial requests without cached data, so an old response cannot overwrite the reset or terminal refresh. Business reads do not need to succeed before the checkpoint advances. Errors and aborted batches preserve the last processed position; an AbortSignal check rejects late work after cache clear or session unmount. Query cache retains only the cursor and active count, without a growing operation history or ID set. Checkpoints do not expire while logged in and clear with the authentication cache.

First entry, changed backend instance and unavailable notification history return an explicit reset and a fixed new starting cursor. Reset invalidates the operation-related feature prefixes and changes a global map image token; notifications committed during business refresh remain available after the reset cursor. Local authored editor state stays in its existing edit session. Task progress, completion messages and retained results continue through their feature/task interfaces. `RebuildProgressDialog`, populate/compression/ownership presentation and world restore/prune views delegate business completion to the observer.

## Resource ownership

Files and world publish their own terminal resource mappings. File keys scope
invalidation by server; explicit global file-root resources refresh all affected
server caches. Archive-root resources alone do not invalidate unrelated servers.
Synchronous local CRUD and browser-owned partial uploads retain immediate write
invalidation independently of the durable-task observer.

Map initialization terminal outcomes refresh the server's map status and region
queries even after navigation. Individual `map_render` operations do not
invalidate map queries, which would trigger another render cycle.

## Browser tile revisions

`features/world/map/revision.ts` stores the newest relevant notification sequence and operation ID for each server and global scope in Query cache. Feed sequence determines arrival order independently of server time; later effective changes of one terminal operation still change the tile URL. A separate global reset token changes on bootstrap or lost history, resets sequence comparison baselines and remains independent of server/global timestamps. Tile URLs combine these tokens with MCA mtime, so MCC-only changes, same-mtime replacements and lost-notification recovery refresh browser images. Read-only previews and snapshots leave the input revision unchanged.

## Verification

Real QueryClient/MSW tests verify off-page partial-write completion, pagination,
reconnect, reset, cancellation and logout isolation. See
[frontend testing](testing.md) for their ownership and targeted invocation.
