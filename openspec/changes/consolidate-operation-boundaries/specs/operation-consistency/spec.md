## Purpose

Keep normal server administration operations coherent from preparation through observable completion while preserving existing feature scope and practical recovery boundaries.

## ADDED Requirements

### Requirement: Configuration preview and application agree
The system SHALL use the server's retained template snapshot for ordinary parameter preview and saving, and SHALL preserve explicit source-template upgrades and direct/template conversion.

#### Scenario: Source template changed or deleted
- **WHEN** a user edits a server whose source template has changed or been deleted
- **THEN** preview and saving use the server snapshot unless an explicit upgrade is requested

### Requirement: Configuration completion includes its metadata
The system SHALL report configuration task success only after required metadata corresponds to the applied configuration, and SHALL preserve whether the server was intended to be running.

#### Scenario: Edit after stopping
- **WHEN** a user stops a server and applies valid changed configuration
- **THEN** the configuration is applied successfully and the server remains stopped

#### Scenario: Startup fails after configuration is applied
- **WHEN** applying configuration succeeds but restarting the server fails
- **THEN** the task reports failure and the stored configuration source still corresponds to the applied configuration

### Requirement: Destructive world maintenance owns its server scope
The system SHALL prevent starting a server during destructive maintenance of its world, coordinate scheduled backups with the affected server scopes, and retain ordinary online file restoration.

#### Scenario: Start during pruning
- **WHEN** a user requests startup while a prune application owns that server
- **THEN** startup is rejected and becomes available again after maintenance ends

#### Scenario: Ordinary online file restore
- **WHEN** a running server restores an ordinary configuration file outside its world directories
- **THEN** online restoration remains available

#### Scenario: Scheduled backup skips during maintenance
- **WHEN** a scheduled single-server or global backup cannot acquire its affected server scopes
- **THEN** it creates no snapshot and records a terminal `skipped` execution with its reason
- **AND** execution history displays the result as skipped rather than successful

### Requirement: Restore completion and cancellation are observable
The system SHALL close the execution and record a terminal history status when an active restoration is cancelled or fails. Selected source world data SHALL be restorable even when its destination directory is absent.

#### Scenario: Client disconnects during restore
- **WHEN** an active restore stream is closed
- **THEN** its execution is closed, its maintenance ownership is released and its history no longer claims it is running

#### Scenario: Missing entities or poi directory
- **WHEN** selected snapshot content contains sidecar data whose entire destination directory is missing
- **THEN** restoration includes that data and rollback can restore the prior missing state

### Requirement: Upload flows own their local activity and outputs
The system SHALL keep each upload flow's checking, batching, pause/resume and cancellation coherent, retain serial batch behavior, and give independent compression tasks independent output files.

#### Scenario: Repeated checking action
- **WHEN** conflict checking is still in progress
- **THEN** the same upload flow cannot start a second check-and-upload operation

#### Scenario: Separate compression tasks
- **WHEN** two tasks compress the same source within one timestamp interval
- **THEN** their output files are distinct

### Requirement: Deleted identities lose access
The system SHALL reject subsequent authenticated requests using sessions belonging to deleted users while preserving the master-token protocol.

#### Scenario: Deleted user keeps an open browser
- **WHEN** the user is deleted and its old browser session requests its identity
- **THEN** the request is unauthorized

### Requirement: Local configuration and file failures have bounded effects
The system SHALL reject newly submitted invalid template or log-parser definitions and SHALL keep unaffected directory entries visible when one entry disappears.

#### Scenario: Invalid parser definition
- **WHEN** a submitted rule cannot compile or lacks required extraction groups
- **THEN** saving fails with a validation error and the prior configuration remains effective

#### Scenario: Directory entry disappears
- **WHEN** a listed directory entry cannot be read because it no longer exists
- **THEN** other entries remain available

### Requirement: DNS manager honors the effective enabled state
The system SHALL perform no new automatic DNS writes after a disabled configuration is observed and SHALL settle each update's work before allowing a subsequent update.

#### Scenario: Hot disable followed by server administration
- **WHEN** enabled DNS management is disabled and a server lifecycle action occurs
- **THEN** that action causes no DNS or router writes

### Requirement: Player history remains usable across cleanup and recovery
The system SHALL preserve increasing chat replay identifiers across cleanup and SHALL not calculate negative playtime during crash recovery.

#### Scenario: Cleanup removes the highest chat identifier
- **WHEN** new chat arrives after cleanup removed the highest stored identifier
- **THEN** a client using its previous cursor can replay the new chat

#### Scenario: Join follows the last heartbeat
- **WHEN** crash recovery ends a session that began after the recorded heartbeat
- **THEN** the session ends no earlier than its join time and contributes nonnegative playtime

### Requirement: Finite progress flows terminate visibly
The frontend SHALL leave its active state when a finite progress stream ends without its required terminal event.

#### Scenario: Premature progress EOF
- **WHEN** map initialization or restore preview closes before completion
- **THEN** the user sees a recoverable failure and can close or retry the flow

### Requirement: E2E phase budgets reflect actual work
The runner SHALL reserve capacity before starting the deployment deadline, let long streams use their operation deadline, and provide diagnostics and resource cleanup independent bounded budgets.

#### Scenario: Capacity queue exceeds setup duration
- **WHEN** a case waits for a Minecraft slot longer than its setup budget but remains within the run deadline
- **THEN** it receives its setup budget after capacity is acquired

#### Scenario: Diagnostic timeout
- **WHEN** diagnostics exhaust their deadline
- **THEN** resource cleanup still starts with an unexpired deadline and the diagnostic failure remains reported
