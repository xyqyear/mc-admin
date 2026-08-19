# Cron Scheduling Specification

## Purpose

Defines how MC Admin accepts, stores, displays, validates, and executes conventional crontab weekday expressions consistently across every cron job lifecycle path.

## Requirements

### Requirement: Conventional weekday numbering

The system SHALL interpret the fifth field of every five-field cron expression using conventional crontab weekday numbering, where `0` and `7` mean Sunday, `1` means Monday, and `6` means Saturday. Case-insensitive weekday names SHALL identify the named calendar day without numeric reinterpretation.

#### Scenario: Numeric Monday

- **WHEN** a user creates an active job with weekday field `1`
- **THEN** the job's eligible fire times fall on Monday

#### Scenario: Sunday aliases

- **WHEN** a user creates jobs with weekday field `0` or `7`
- **THEN** both jobs have eligible fire times on Sunday

#### Scenario: Named weekday

- **WHEN** a user creates a job with weekday field `mon`
- **THEN** the job's eligible fire times fall on Monday

### Requirement: Compound weekday expressions

The system SHALL evaluate weekday lists, ascending ranges, and positive steps against the conventional Sunday-zero domain before scheduling the resulting set of calendar days. Duplicate calendar days, including Sunday expressed as both `0` and `7`, SHALL be deduplicated without changing execution behavior.

#### Scenario: Weekday range

- **WHEN** a job uses weekday field `1-5`
- **THEN** its eligible fire times fall on Monday through Friday

#### Scenario: Range crossing the internal numbering boundary

- **WHEN** a job uses weekday field `0-2`
- **THEN** its eligible fire times fall on Sunday, Monday, and Tuesday

#### Scenario: Wildcard step

- **WHEN** a job uses weekday field `*/2`
- **THEN** its eligible fire times fall on Sunday, Tuesday, Thursday, and Saturday

#### Scenario: List with duplicate Sunday aliases

- **WHEN** a job uses weekday field `0,6,7`
- **THEN** its eligible fire times fall on Saturday and Sunday without duplicate executions for Sunday

### Requirement: Expression preservation

The system SHALL preserve the user-provided cron expression in persistence and API responses while applying weekday normalization only when calculating or registering execution times.

#### Scenario: Create and retrieve a compound expression

- **WHEN** a job is created with cron expression `0 9 * * 1-5`
- **THEN** subsequent API responses and persisted configuration contain `0 9 * * 1-5`
- **AND** the job executes only on Monday through Friday

#### Scenario: Recover an active job

- **WHEN** the application restarts with an active persisted job containing a conventional numeric weekday expression
- **THEN** the job is recovered with the same persisted expression and equivalent conventional weekday execution behavior

#### Scenario: Update or resume a job

- **WHEN** a conventional weekday expression is submitted through update or an existing job is resumed
- **THEN** the resulting active schedule uses the same weekday semantics as job creation

### Requirement: Weekday validation

The system SHALL reject malformed weekday expressions, numeric values outside `0` through `7`, descending ranges, and non-positive steps without creating or replacing an active schedule.

#### Scenario: Out-of-range weekday

- **WHEN** a user submits weekday value `8`
- **THEN** the request fails with a cron validation error
- **AND** no active schedule is created from the invalid expression

#### Scenario: Invalid step

- **WHEN** a user submits weekday field `*/0`
- **THEN** the request fails with a cron validation error
- **AND** no active schedule is created from the invalid expression

#### Scenario: Descending range

- **WHEN** a user submits weekday field `5-1`
- **THEN** the request fails with a cron validation error
- **AND** no active schedule is created from the invalid expression
