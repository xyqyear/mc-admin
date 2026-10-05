# CI Test Planning Specification

## Purpose

Use measured execution history to shorten complete backend, API and browser validation while preserving isolation, cloud recovery and trustworthy release qualification.

## Requirements

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

### Requirement: Integrated DNS qualification
API E2E SHALL own real Huawei scenarios, their costs, execution plans and aggregate qualification. Complete qualification SHALL independently require every current ordinary regression and Huawei scenario and verified owned cloud cleanup. Provider dependency metadata SHALL select required private configuration and recovery steps. Every API shard SHALL use `dns-e2e` as an unrestricted configuration store with no environment protection or branch authorization gate, and provider steps SHALL receive credentials only when required. Ordinary regression SHALL NOT receive cloud credentials or select cloud scenarios.

#### Scenario: Complete qualification omits a required Huawei case
- **WHEN** the complete qualification context requires a current Huawei scenario but its assigned execution is absent, skipped or failed
- **THEN** the API aggregate gate fails

#### Scenario: A pull request executes ordinary regression
- **WHEN** a pull request runs the ordinary API regression profile
- **THEN** its plan excludes cloud scenarios and its test steps are not passed Huawei credentials

#### Scenario: Docker cleanup succeeds but cloud records remain
- **WHEN** owned local containers are removed while a selected Huawei scope lacks verified cloud cleanup
- **THEN** API qualification fails and retains the non-secret recovery evidence

### Requirement: Unified global API scheduling
The API planner SHALL globally allocate every selected atomic group for a profile into one immutable plan and one job matrix. It SHALL retain Fresh/reusable group boundaries, permit ordinary and Huawei groups in the same shard, and use at most 16 shards and eight concurrent jobs with two workers and one Minecraft slot per runner. Provider requirements SHALL supply dependency metadata and credential/recovery bindings without imposing separate shard allocation or provider-specific concurrency limits. DNSPod and Mojang SHALL remain explicitly selected profiles.

#### Scenario: Ordinary and Huawei work share capacity
- **WHEN** a qualification plan selects ordinary and Huawei groups
- **THEN** the planner may place them together using the same cost and resource model while retaining each atomic group and exact-once coverage

#### Scenario: A shard has a Huawei dependency
- **WHEN** an assigned shard contains ordinary groups and a Huawei group
- **THEN** its provider steps receive the required configuration and it executes all assigned groups under the same worker and Minecraft limits, with verified owned cloud recovery

#### Scenario: Placement changes but timing semantics stay compatible
- **WHEN** previously audited api-lifecycle-v2 individual/group costs and the fixture/resource compatibility fingerprint match the current profile
- **THEN** the global planner reuses those costs, including reusable-group lifecycle floors, without reusing historical assignments or candidate receipts

### Requirement: Durable timing evidence after audited execution
The system SHALL retain per-case execution timings, fixture costs, outcomes and source identity, and publish reusable timing history only after the family's full audit succeeds. Each following run SHALL freeze the selected historical source before shard execution.

#### Scenario: A successful execution informs the next run
- **WHEN** all current selected cases, shards and cleanup pass the family's audit
- **THEN** its measured costs become available to the next comparable plan without editing repository weights
