## MODIFIED Requirements

### Requirement: Authenticated current-state task event stream

The system SHALL provide authenticated SSE observation of task summaries,
including an initial current-state snapshot, subsequent structured progress/state
updates and task removals. Summaries SHALL preserve nullable progress. Event
tasks SHALL explicitly indicate whether their authoritative result is included;
only known results of settled terminal tasks within the bounded result size
SHALL be included. Running tasks SHALL NOT expose results as settled, even at
100 percent progress. Slow observers SHALL have bounded buffering and recover by
resynchronizing current state without blocking workers. Intermediate updates
may coalesce; the stream SHALL NOT promise a durable history of progress frames.

#### Scenario: First connection and reconnect
- **WHEN** an authenticated observer connects or reconnects
- **THEN** it receives the current task snapshot and subsequent updates
- **AND** no task is submitted or replayed by observing it

#### Scenario: Slow or idle observer
- **WHEN** updates exceed an observer's buffer or work becomes idle
- **THEN** the observer resynchronizes bounded pending updates or receives keepalive
- **AND** worker execution and other observers continue independently

#### Scenario: Access is denied
- **WHEN** an unauthenticated request opens task observation
- **THEN** access is rejected using the existing task authorization policy

#### Scenario: Structured progress before settlement
- **WHEN** a map stage, self-check finding, hash byte count or batch item count changes during execution
- **THEN** current structured progress is observable without a task detail request
- **AND** an intermediate result or 100 percent progress does not imply completion

#### Scenario: Bounded final result
- **WHEN** a task settles with a known result within the size limit
- **THEN** its event explicitly includes the authoritative result
- **AND** larger or not-yet-loaded results are explicitly marked as excluded

### Requirement: Shared client observation and authoritative results

Task lists, detail views, initiating workflows and execution indexes SHALL share
one task SSE connection per active application data client. Observation SHALL
replace periodic task-progress polling and per-progress detail reads. The client
SHALL retain HTTP reads for initial or retained details and terminal results
excluded from events. Task data SHALL remain in the existing server-state cache.
A terminal observation SHALL NOT complete a result-consuming workflow until its
authoritative result is available from an event or detail read. Reconnection
and repeated events SHALL NOT resubmit work.

#### Scenario: Concurrent task consumers
- **WHEN** several task views and workflows observe work concurrently
- **THEN** they share the connection and receive current progress
- **AND** normal progress does not require periodic or per-event detail reads

#### Scenario: Final detail cannot be read yet
- **WHEN** a terminal update excludes its result and its detailed result read fails
- **THEN** the initiating workflow remains guarded until a later observation or explicit retry obtains the result
- **AND** it consumes the complete result only after confirmed terminal detail

#### Scenario: Stream failure and session replacement
- **WHEN** the connection fails or the authenticated session ends
- **THEN** recoverable failures use bounded reconnect without periodic HTTP progress fallback
- **AND** an ended session closes observation and cannot write late updates into a replacement session's cache

#### Scenario: Result read retry after dismissal
- **WHEN** a completed task excludes its result and its list entry is dismissed before complete result retrieval
- **THEN** a result consumer can explicitly retry reading the same retained task
- **AND** the client preserves the true execution status and does not resubmit the operation

#### Scenario: Result retrieval temporarily fails
- **WHEN** an authoritative terminal result cannot be read
- **THEN** the task center and initiating workflow expose a retry action and a result-read failure state
- **AND** actions requiring the complete result remain guarded until successful retrieval

## ADDED Requirements

### Requirement: Bounded task history and progress

Runtime task history and streamed progress details SHALL have bounded retention or size. Completed execution handles SHALL be released. Live and HTTP observations SHALL agree on retained result availability; absent or expired history SHALL have an explicit consistent outcome. Successful historical restoration associations SHALL NOT indefinitely prevent journal retention, while genuine unresolved recovery obligations SHALL remain protected.

#### Scenario: Repeated completed work
- **WHEN** successful tasks exceed the recent-history capacity
- **THEN** runtime handles and streamed history remain bounded
- **AND** authoritative retained details remain readable until durable expiration

#### Scenario: Large cumulative progress
- **WHEN** cumulative progress evidence grows beyond the event budget
- **THEN** current progress remains bounded and complete evidence is available through result reads after settlement
- **AND** reconnect does not retransmit unbounded terminal evidence

### Requirement: Recoverable task-center presentation

The task center SHALL distinguish confirmed empty state from unknown or disconnected observation, expose task-command failures, and provide retained per-item result inspection after navigation. Task actions opened from a modal SHALL remain operable within modal focus and interaction constraints. Safe authored task failure information SHALL survive restart without exposing raw internal errors.

Task timestamps SHALL identify an unambiguous instant so recent-history visibility
and ordering remain correct when the browser and server use different timezones.

#### Scenario: Observation unavailable
- **WHEN** initial task observation fails or an established connection is lost
- **THEN** the task center reports unavailable or stale state and provides recovery
- **AND** it does not present unknown state as a confirmed empty list

#### Scenario: Partial operation results after navigation
- **WHEN** an operation completes with per-item failures and the initiating page is left
- **THEN** its retained task result still provides the failed items and authored error descriptions

#### Scenario: Task command fails
- **WHEN** cancellation or task dismissal is rejected or cannot be delivered
- **THEN** the user receives failure feedback and can retry
- **AND** cancellation acceptance alone does not establish terminal completion

#### Scenario: Client timezone differs
- **WHEN** a recently completed task is observed from a browser in a different timezone
- **THEN** it remains visible within the same retention window and its elapsed time is correct
