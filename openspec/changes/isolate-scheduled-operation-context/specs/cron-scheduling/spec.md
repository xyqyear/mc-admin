## ADDED Requirements

### Requirement: Independent scheduled operation ownership

The system SHALL execute each scheduled occurrence with its own durable operation identity and declared resource scope, independently of any operation that created, updated or resumed a schedule. Changing a schedule SHALL NOT transfer the caller's operation to existing or newly registered jobs.

#### Scenario: Server creation registers a restart schedule

- **WHEN** server creation registers a restart schedule and completes before existing backup and self-check schedules fire
- **THEN** each scheduled occurrence owns a distinct operation linked to its execution history
- **AND** a successful backup retains restorable source bytes and the self-check retains its findings
- **AND** the completed server creation record remains unchanged

### Requirement: Cron terminal history belongs to the occurrence

The system SHALL derive a scheduled occurrence's terminal history only from its own execution outcome or its own durable operation. Another operation's success SHALL NOT replace an occurrence's failure.

#### Scenario: Backup fails after successful server creation

- **WHEN** a scheduled backup cannot read its configured source after server creation has completed
- **THEN** its execution and its own operation record are failed with safe public diagnostics
- **AND** no snapshot is attributed to the failed backup

#### Scenario: Cancellation arrives after committed success

- **WHEN** an occurrence has durably committed success before cancellation is observed
- **THEN** its history retains that committed success while cancellation still propagates through worker cleanup
