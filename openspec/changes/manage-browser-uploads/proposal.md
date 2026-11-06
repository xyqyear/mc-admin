## Why

Closing the file upload dialog currently aborts transfer, while archive uploads prevent dismissal. Both workflows should remain observable without blocking navigation, including a visible cue when a dialog moves into the task center (#160).

## What Changes

- Keep file and archive upload workflows alive across dialog dismissal and application navigation within the authenticated browser session.
- Add an upload tab with one clickable progress heading per entry, pending decisions and retained results; the heading reopens the same workflow.
- Separate hiding from explicit cancellation and preserve each protocol's completion and partial-write guarantees.
- Animate dismissed upload dialogs towards the movable task-center launcher, with the original immediately hidden and reduced motion respected.
- Non-goals: changing upload APIs, adding ordinary-file resumability, transferring bytes after browser shutdown, or persisting browser File objects.

## Capabilities

### New Capabilities

- `browser-upload-management`: Session-owned upload presentation, discovery, reopening, cancellation and minimizing feedback.

### Modified Capabilities

None. Existing upload protocol and server-task guarantees remain applicable.

## Impact

Frontend task-center state/UI, application composition, file/archive upload dialogs and controllers, targeted tests and feature documentation. No backend API, database, configuration or Docker changes; no new dependencies.
