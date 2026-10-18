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
