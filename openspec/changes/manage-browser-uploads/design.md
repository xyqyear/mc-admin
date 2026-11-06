## Context

See proposal.md for motivation. Current ownership is described in frontend-react/docs/task-center.md, archive-upload.md, file-management.md and data-architecture.md. The two upload protocols have different completion and cancellation semantics; backend tasks already have a shared observer.

## Goals / Non-Goals

Preserve existing protocol controllers and business invariants while separating dialog visibility from controller lifetime. Do not introduce a backend workflow engine, a second server-task cache, or cross-reload browser transfer persistence.

## Decisions

- Add a browser-only upload registry to the tasks feature, exposed through a public upload entry. It owns identities, captured inputs, list summaries and the visible upload identity. Existing feature controllers remain the protocol owners.
- Mount one feature upload controller per retained registry record in the authenticated application shell. Hiding only changes visibility; the hook and overwrite-decision state remain mounted. Multiple uploads keep independent immutable destinations. Unstarted dismissed drafts can be discarded; started and terminal workflows remain reopenable until explicitly cleared.
- Retain the original file batch and archive chunk sequencing. Report transport, verification and finalization separately; render ordinary per-file failures as an unsuccessful summary while retaining the complete results.
- Let the upload dialog request minimization through the task-center entry. Animate a noninteractive, accessibility-hidden visual copy to the launcher's measured rectangle using browser animation APIs, then remove it. Close the real dialog immediately. Missing APIs or reduced motion skip movement and retain textual feedback. Use the current draggable position, not fixed bottom-right coordinates.
- Retained workflow records hold native File references only in memory. Removing settled entries and authenticated-host teardown unmount the controllers and release their inputs; backend task data remains in Query. Logout does not cancel already accepted server hashing/publication implicitly.
- Update task-center, file, archive and data-architecture documentation. Public upload imports extend the frontend boundary policy; no generated UI changes or new dependencies are required.

## Risks / Trade-offs

- A hidden controller could accidentally reset on visibility changes → keep execution's logical lifetime separate from presentation and test delayed HTTP completion across navigation/reopening.
- Completion callbacks could lose the original target → capture server/path per registry record and retain independent cache invalidation.
- Large native-file references can remain until dismissed → offer terminal-record removal and clearing; never serialize files/controllers.
- Visual copies can intercept interaction or outlive logout → use inert/aria-hidden copies, bounded cleanup and host teardown cleanup; reduced motion bypasses movement.

## Migration Plan

No persisted data or API migration is required. Deploy the frontend and backend together as usual. Rollback restores the previous dialog behavior without data conversion; active browser transfers require keeping the current page alive.
