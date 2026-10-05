## Purpose

Use measured execution history to shorten complete backend, API and browser validation while preserving isolation, cloud recovery and trustworthy release qualification.

## ADDED Requirements

### Requirement: Automatic planning from comparable successful history
The system SHALL build each test family's current plan from its complete current inventory and the latest available comparable, successfully audited execution history. Historical data SHALL affect costs and placement only. Missing history and new tests SHALL use positive fallback estimates.

#### Scenario: A new case has no historical sample
- **WHEN** the current inventory contains a case absent from the restored history
- **THEN** the plan includes it exactly once with a positive fallback cost

#### Scenario: The previous execution failed or was incomplete
- **WHEN** an execution failed, was cancelled, skipped cases or lacks complete coverage evidence
- **THEN** it cannot replace the successful historical costs used for subsequent plans

### Requirement: Bounded five-minute execution target
The system SHALL automatically choose shard counts targeting 300 seconds of execution including fixture initialization and cleanup, separately from CI installation and queueing. The target SHALL NOT shorten business deadlines or fail otherwise successful tests. Indivisible oversized units and fixed overhead SHALL be reported, with bounded shard counts and concurrency.

#### Scenario: More shards can meet the target
- **WHEN** the estimated allocation exceeds 300 seconds and additional eligible shards can reduce it
- **THEN** the planner creates additional shards within the configured limits

#### Scenario: One indivisible unit exceeds the target
- **WHEN** an indivisible test or fixture group exceeds the target
- **THEN** it remains complete in one shard and the plan reports the unmet target without endlessly increasing shards

### Requirement: Immutable execution plans and exact coverage
Every execution SHALL use one immutable plan and historical snapshot for its family. Final qualification SHALL reject missing, duplicated, unexpected, unsuccessful or skipped cases, inconsistent plans and unverified resource cleanup.

#### Scenario: A browser shard omits a journey
- **WHEN** the shard reports other journeys as successful but omits an assigned journey
- **THEN** aggregate qualification rejects the incomplete execution

#### Scenario: Two shards use different historical snapshots
- **WHEN** shard evidence does not match the family's shared plan identity
- **THEN** the aggregate audit rejects it

### Requirement: Integrated protected DNS qualification
API E2E SHALL own real Huawei scenarios, their costs, execution plans and aggregate qualification. Complete qualification SHALL require every current Huawei scenario and verified owned cloud cleanup. Ordinary untrusted validation SHALL NOT receive cloud credentials or select protected cloud scenarios.

#### Scenario: Complete qualification omits the cloud partition
- **WHEN** the complete qualification context requires Huawei scenarios but their partition is absent, skipped or failed
- **THEN** the API aggregate gate fails

#### Scenario: A pull request executes ordinary regression
- **WHEN** an untrusted pull request runs API regression
- **THEN** its plan excludes protected cloud scenarios and its jobs receive no Huawei credentials

#### Scenario: Docker cleanup succeeds but cloud records remain
- **WHEN** owned local containers are removed while a selected Huawei scope lacks verified cloud cleanup
- **THEN** API qualification fails and retains the non-secret recovery evidence

### Requirement: Durable timing evidence after audited execution
The system SHALL retain per-case execution timings, fixture costs, outcomes and source identity, and publish reusable timing history only after the family's full audit succeeds. Each following run SHALL freeze the selected historical source before shard execution.

#### Scenario: A successful execution informs the next run
- **WHEN** all current selected cases, shards and cleanup pass the family's audit
- **THEN** its measured costs become available to the next comparable plan without editing repository weights
