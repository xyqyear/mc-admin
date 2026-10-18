# Execution observation Specification

## Purpose

Provide current restoration and chunk-prune execution discovery through shared authenticated observation, retaining destructive-action guards across reconnects and preview lifecycle changes.

## Requirements

### Requirement: Complete restoration discovery

The shared event stream SHALL include every active restoration relevant to its authorized scope, including global restorations and their target server identities. Successful acceptance and real terminal settlement SHALL update that index. Observing or losing an index entry SHALL NOT itself execute, cancel or establish completion of a restoration.

#### Scenario: Accepted restoration and late observer
- **WHEN** a restoration is accepted and another page begins observing afterward
- **THEN** its current snapshot identifies the restoration and affected servers without periodic discovery reads
- **AND** the UI retains protection until authoritative task settlement

#### Scenario: Discovery interrupted
- **WHEN** initial discovery or reconnect fails
- **THEN** discovery remains unknown and retained active task references remain guarded
- **AND** a failed snapshot is not represented as an authoritative empty list

### Requirement: Chunk-prune lifecycle observation

The shared event stream SHALL provide current preview/apply tasks, structured progress and preview availability for each relevant server. Preview registration, expiry, consumption, stale detection and eviction SHALL update observation without periodic state reads. Dismissal from a task list SHALL NOT erase retained preview state. Preview geometry and actions SHALL remain separately fetched business data, and destructive application SHALL retain authoritative input validation.

#### Scenario: Preview completes and expires
- **WHEN** a preview settles successfully and later reaches its validity deadline
- **THEN** its retained task and bounded result become available to observers
- **AND** expiry updates availability without requiring user action or polling

#### Scenario: Concurrent application or stale inputs
- **WHEN** a preview is consumed by apply or its inputs fail validation
- **THEN** observers receive the consumed or stale state
- **AND** no competing or stale application bypasses backend validation

#### Scenario: Late observer after task dismissal
- **WHEN** a valid preview task has been dismissed from the general task list
- **THEN** a new prune observer still receives retained preview identity and availability
- **AND** reconnection does not submit a second preview or apply operation
