## ADDED Requirements

### Requirement: Completed operations cannot authorize later work

The system SHALL reject nested work that attempts to reuse an ended operation. Independent long-lived producers SHALL execute their own business work without inheriting the operation that started them, while valid nested work SHALL retain its active operation and covering resource ownership.

#### Scenario: Ended parent context is reused

- **WHEN** nested work is invoked under an operation that is already ended
- **THEN** the work is rejected before its effects
- **AND** the ended operation record remains unchanged

#### Scenario: Log observation outlives server creation

- **WHEN** server creation starts log observation and completes before player events arrive
- **THEN** later player events remain persisted and observable
- **AND** processing them does not reuse or modify the completed creation operation
