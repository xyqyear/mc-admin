## Purpose

Let administrators understand and observe long non-snapshot management work without keeping the initiating page connected, while preserving resource safety, meaningful results and the existing task center.

## ADDED Requirements

### Requirement: Long management work has detached acceptance

The product SHALL submit server lifecycle commands including creation and removal, server registry synchronization, recursive server/archive deletion, map initialization, manual self-check, manual DNS/router synchronization and server-side upload hashing as background tasks. Acceptance SHALL identify the task before the long execution finishes. Accepted work SHALL survive loss of the submitting browser connection while the backend remains running.

#### Scenario: Startup needs an image
- **WHEN** an administrator starts a stopped server whose image preparation is slow
- **THEN** the interface promptly identifies the accepted startup task and displays its current activity before a Minecraft container reports starting
- **AND** navigating away does not cancel the accepted task

#### Scenario: Lost acceptance response
- **WHEN** the connection closes after task acceptance but before the response reaches the browser
- **THEN** the accepted task remains discoverable with its target and action
- **AND** retrying does not execute a concurrent conflicting copy

#### Scenario: Existing detached operation
- **WHEN** an administrator rebuilds, populates, compresses, repairs ownership or applies chunk pruning
- **THEN** the existing task is discoverable through the same task center without a duplicate execution or duplicate task

### Requirement: Existing blocking and progress interactions are preserved

Moving execution to a background task SHALL preserve the initiating workflow's existing blocking scope, disabled actions, dialog-close restrictions and terminal behavior. Existing streaming progress views SHALL remain visible and obtain progress and outcomes from task status. Task acceptance SHALL NOT unblock the workflow or replace its progress view with only a task-center notification. Status-read failure SHALL NOT be treated as task completion or as permission to repeat the operation.

#### Scenario: Acceptance returns before a blocking operation finishes
- **WHEN** a previously blocking operation returns a task ID while the task is pending or running
- **THEN** the original loading state, disabled actions and close restrictions remain in force without an idle gap
- **AND** no success callback, automatic navigation or completion-driven dialog dismissal occurs

#### Scenario: A previously streamed progress view observes a task
- **WHEN** an operation that previously displayed streamed progress is executing as a task
- **THEN** the same progress surface displays the task's stage, progress and result while preserving its existing interaction restrictions
- **AND** the user does not have to leave that surface to open the task center

#### Scenario: Status polling temporarily fails
- **WHEN** the UI cannot read the status of an accepted task
- **THEN** it shows an observation or connection problem and retains the last known blocking state
- **AND** it reconciles the same task without declaring the operation finished or enabling duplicate submission

#### Scenario: The task reaches a confirmed terminal outcome
- **WHEN** the UI observes completion, failure or settled cancellation
- **THEN** it applies the original workflow's corresponding terminal behavior using that result
- **AND** it does not close a result view that previously required explicit dismissal

#### Scenario: A running progress dialog was previously non-dismissible
- **WHEN** the user attempts to close that dialog while the task is active
- **THEN** its existing close restriction remains in force despite independent backend execution

#### Scenario: Browser refresh interrupts observation
- **WHEN** a browser refresh interrupts observation of an accepted task
- **THEN** execution continues independently and the returning workflow reads that task's current state
- **AND** an active task restores the applicable blocking state without submitting a new operation

### Requirement: Execution feedback describes actual work

Tasks SHALL expose a readable action, target, current stage, elapsed time and eventual outcome. A measurable stage SHALL use actual progress; an unmeasurable stage SHALL remain indeterminate. Acceptance SHALL NOT be presented as completion. Completing Docker startup work SHALL NOT be presented as Minecraft being healthy unless readiness has actually been observed.

#### Scenario: Unmeasurable Docker preparation
- **WHEN** Docker provides no reliable total for the current startup stage
- **THEN** the interface displays a preparation message and elapsed time without fabricated percentage progress

#### Scenario: Minecraft starts after Docker completes
- **WHEN** the startup command has finished but Minecraft is still initializing
- **THEN** task completion and the separate server readiness status remain distinguishable

#### Scenario: Self-check finds a problem
- **WHEN** a manual self-check finishes and reports failing checks
- **THEN** the task result preserves the check findings and does not claim the server passed all checks merely because the checker completed

### Requirement: Maintenance feedback explains unavailable actions

Affected controls SHALL show an understandable reason for unavailability without requiring hover. When an active task owns the conflicting operation, the user SHALL be able to locate that task. Request-owned snapshot work, scheduled work and recovery blocks SHALL retain readable reasons even when no task link exists. Safe reads and unrelated work SHALL remain available under existing resource and UI rules; task conversion SHALL NOT relax existing blocking interactions.

#### Scenario: Another administrator is starting the server
- **WHEN** a server is occupied by an accepted startup task
- **THEN** another administrator sees why conflicting actions are unavailable and can locate its progress

#### Scenario: Recovery ownership is uncertain
- **WHEN** an interrupted operation retains a recovery block
- **THEN** the interface explains that recovery is required instead of suggesting that an ordinary running task is still making progress

### Requirement: Deferred execution preserves target and admission checks

Submission and execution SHALL preserve authorization, confirmed parameters, confined paths and exact server instance identity. Conflicting lifecycle submissions SHALL be rejected or associated with an existing task rather than accumulated for surprising later execution. Destructive work SHALL revalidate its target before writing. Creation and registry synchronization SHALL account for absent targets and all affected server instances.

#### Scenario: Unauthorized synchronization
- **WHEN** a user without the existing required role submits registry synchronization
- **THEN** acceptance is rejected without starting a task or changing any server

#### Scenario: Server name is reused before execution
- **WHEN** a delayed task targets an instance that has been removed and replaced under the same public name
- **THEN** it fails without modifying the replacement instance

#### Scenario: Conflicting lifecycle clicks
- **WHEN** two clients concurrently request conflicting lifecycle actions for the same server
- **THEN** at most one conflicting action proceeds and the other client receives actionable busy feedback

#### Scenario: Unrelated ordinary file operation
- **WHEN** a long task owns only a particular file subtree
- **THEN** ordinary reads and nonconflicting file work remain available under existing access rules

### Requirement: Deletion does not wait on itself

A server removal task SHALL freeze new conflicting work and settle existing writers before deletion. Its own execution SHALL NOT be treated as an unrelated task to cancel or drain. If another writer cannot settle, removal SHALL fail visibly without deleting the server's files.

#### Scenario: Removal is the only active task
- **WHEN** a removal task is the only active task for an eligible server
- **THEN** it can complete without cancelling itself or timing out waiting for itself

#### Scenario: Another writer does not stop
- **WHEN** a conflicting writer cannot be confirmed stopped during removal
- **THEN** removal reports the conflict and preserves the files

### Requirement: Cancellation and restart preserve truthful outcomes

The UI SHALL offer cancellation only for operations with a defined safe cancellation boundary. Cancellation SHALL NOT imply rollback. A terminal state SHALL be published only after required execution and cleanup settle. After backend restart, accepted incomplete work SHALL be reported as interrupted or another verifiable terminal outcome and SHALL NOT be silently replayed.

#### Scenario: Non-cancellable recursive deletion
- **WHEN** deletion has entered a filesystem operation that must finish before releasing ownership
- **THEN** the UI does not offer immediate cancellation or claim that closing the panel stops deletion

#### Scenario: Backend restarts during startup
- **WHEN** the backend restarts while a startup task has unresolved Docker work
- **THEN** its history exposes interruption or verified completion and retains required resource protection
- **AND** it does not automatically issue the startup command again

### Requirement: Results and state remain available across navigation

Task results SHALL remain discoverable after navigation or refresh. Terminal outcomes, including failures after partial writes, SHALL refresh affected server, file, map, DNS and self-check views independently of the initiating page. Feature-specific details SHALL remain available through their existing result/history views.

#### Scenario: Directory deletion completes after navigation
- **WHEN** a user leaves the file browser during deletion and later returns
- **THEN** the listing reflects the actual final contents and the task outcome is available

#### Scenario: Synchronization has mixed outcomes
- **WHEN** registry synchronization adopts some servers and fails for others
- **THEN** users can inspect the per-server results and the server list refreshes to reflect actual changes

### Requirement: Upload hashing owns its input lifetime

Server-side upload hashing SHALL continue independently after the bytes have been received. The task SHALL retain its exact upload input until hashing settles, expose measurable progress and associate the digest with that upload. Explicit upload cancellation SHALL settle hashing before removing its input. Upload verification and final publication SHALL retain their existing conflict and integrity checks.

#### Scenario: Page closes during hashing
- **WHEN** an uploaded archive is being hashed and the page closes
- **THEN** hashing continues and the result can be associated with the upload when the page returns

#### Scenario: Upload is cancelled during hashing
- **WHEN** the user explicitly cancels an upload with active hashing
- **THEN** cleanup settles the hashing reader before deleting its temporary input

### Requirement: Task APIs replace unused execution endpoints while preserving snapshot behavior

The product UI and API test callers SHALL use task acceptance and task-status reads for covered operations. Unused synchronous execution and event-stream endpoints SHALL be removed without old-client compatibility adapters; backend and frontend SHALL deploy together. Domain authorization and validation SHALL remain enforced. This change SHALL NOT alter snapshot creation, restore, restore preview, rollback or repository maintenance execution semantics, ignored-path protection or retained restoration history.

#### Scenario: Covered lifecycle action returns task acceptance
- **WHEN** a valid client submits a lifecycle action
- **THEN** it receives a task identifier and reads completion from task status
- **AND** no alternate synchronous compatibility mode is required

#### Scenario: Snapshot operation remains request-owned
- **WHEN** a user restores world data through the existing snapshot workflow during this rollout
- **THEN** its safety snapshot, stream ownership, interruption and rollback behavior remain unchanged

#### Scenario: Unauthenticated task access
- **WHEN** an unauthenticated client submits or reads one of the covered tasks
- **THEN** access is denied under the existing authentication rules
