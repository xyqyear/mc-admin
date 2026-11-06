## Purpose

Allow administrators to continue observing and controlling browser uploads while using other application pages, without losing transfer state when a dialog closes.

## ADDED Requirements

### Requirement: Uploads outlive their presentation

The application SHALL preserve each started file or archive upload when its dialog is dismissed or the user navigates within the authenticated application. The upload SHALL retain its original target, selected files, overwrite decisions and serial protocol execution. Reopening SHALL NOT submit duplicate work.

#### Scenario: Hide and reopen a transfer
- **WHEN** an administrator closes a running upload and navigates to another server
- **THEN** transfer continues towards the original target and the task center reopens the same workflow with current progress

#### Scenario: Pending conflict decisions
- **WHEN** an upload awaiting overwrite decisions is hidden and reopened
- **THEN** the selected decisions remain available and no conflicting bytes are submitted without confirmation

### Requirement: Upload tasks expose real outcomes

The task center SHALL provide an upload tab showing active stages, paused or retrying work, pending decisions and retained terminal results. Explicit cancellation SHALL remain distinct from hiding. Partial ordinary-file results SHALL be retained; transmitted bytes or accepted archive hashing/publication SHALL NOT by themselves represent success.

#### Scenario: Archive waits for publication
- **WHEN** archive bytes are fully transmitted but verification or publication is unsettled
- **THEN** the upload remains active until the real publication result is available

#### Scenario: Explicitly cancel ordinary upload
- **WHEN** an administrator explicitly cancels an ordinary upload
- **THEN** further browser transfer stops, already written files remain, and the affected directory is refreshed

### Requirement: Minimizing communicates the task destination

Closing an active upload dialog SHALL animate a shrinking representation towards the current task-center launcher position and make the upload tab discoverable. The feedback SHALL respect reduced-motion preferences and SHALL NOT block hiding or upload execution when animation is unavailable.

#### Scenario: Launcher has moved
- **WHEN** the user dismisses an upload after dragging the launcher
- **THEN** the animation ends at the launcher's actual position and the same upload can be reopened there

#### Scenario: Reduced motion
- **WHEN** reduced motion is enabled and an upload dialog is dismissed
- **THEN** the dialog hides without the moving animation and a textual cue identifies the task center

### Requirement: Browser uploads remain session owned

The application SHALL release browser transfer controllers, timers and selected-file references when their records are discarded or the authenticated session ends. It SHALL NOT persist browser file handles or claim transfer survives page reload. Already accepted backend tasks SHALL retain their server-owned execution guarantees.

#### Scenario: Session ends
- **WHEN** authentication expires or the administrator logs out
- **THEN** browser transfer stops and upload records cannot appear in a subsequent authenticated session
