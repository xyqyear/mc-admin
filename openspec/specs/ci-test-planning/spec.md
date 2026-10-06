# CI Test Planning Specification

## Purpose

Use measured execution history to shorten complete backend, API and browser validation while preserving isolation, cloud recovery and trustworthy release qualification.

## Requirements

### Requirement: Automatic planning from comparable successful history
The system SHALL build each test family's current plan from its complete current inventory and the latest available comparable, successfully audited execution history across trusted branches in the same repository, ordered by artifact creation time. Historical sources SHALL match the requested family, execution profile and compatibility fingerprint, and their recorded run, commit and branch SHALL match the artifact. Expired artifacts, fork sources and the current run SHALL be excluded. Historical data SHALL affect costs and placement only. Missing history and new tests SHALL use positive fallback estimates.

#### Scenario: A newer compatible history comes from another branch
- **WHEN** another trusted repository branch has published a newer compatible, successfully audited history than the current branch or main
- **THEN** the planner selects that newer history while deriving required cases from the current inventory

#### Scenario: A new case has no historical sample
- **WHEN** the current inventory contains a case absent from the restored history
- **THEN** the plan includes it exactly once with a positive fallback cost

#### Scenario: The previous execution failed or was incomplete
- **WHEN** an execution failed, was cancelled, skipped cases or lacks complete coverage evidence
- **THEN** it cannot replace the successful historical costs used for subsequent plans

### Requirement: Bounded five-minute execution target
The system SHALL automatically choose shard counts targeting 300 seconds of execution including fixture initialization and cleanup, separately from CI installation and queueing. Each test family SHALL permit at most 16 concurrent shard jobs. Backend planning SHALL permit at most 32 shards; API and browser planning SHALL each permit at most 16 shards. The target SHALL NOT shorten business deadlines or fail otherwise successful tests. Indivisible oversized units and fixed overhead SHALL be reported, with bounded shard counts and concurrency.

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

### Requirement: Integrated provider execution
API E2E SHALL own external-provider scenarios, their costs, execution plans and aggregate audits. Ordinary pull request regression, regular automatic CI and complete qualification SHALL independently require every current API case except DNSPod and verified owned cloud cleanup. Provider dependency metadata SHALL select required private configuration and recovery steps. Every API shard SHALL use `dns-e2e` as an unrestricted configuration store with no environment protection or branch authorization gate, and provider steps SHALL receive credentials only when required.

#### Scenario: Automated API validation omits a required case
- **WHEN** regression or qualification requires a current non-DNSPod scenario but its assigned execution is absent, skipped or failed
- **THEN** the API aggregate gate fails

#### Scenario: A pull request executes ordinary regression
- **WHEN** a pull request runs the ordinary API regression profile
- **THEN** its plan includes every current non-DNSPod case and provider steps receive the configuration and credentials required by their assigned cases

#### Scenario: Docker cleanup succeeds but cloud records remain
- **WHEN** owned local containers are removed while a selected cloud scope lacks verified cloud cleanup
- **THEN** API qualification fails and retains the non-secret recovery evidence

### Requirement: Unified global API scheduling
The API planner SHALL globally allocate every selected atomic group for a profile into one immutable plan and one job matrix. It SHALL retain Fresh/reusable group boundaries, permit groups with different provider dependencies in the same shard, and use at most 16 shards and 16 concurrent jobs with two workers and one Minecraft slot per runner. Provider requirements SHALL supply dependency metadata and credential/recovery bindings without imposing separate shard allocation or provider-specific concurrency limits. CI SHALL offer only `regression`, `qualification` and `dnspod` profiles; only DNSPod SHALL require explicit selection. Local case/tag filters SHALL remain available.

#### Scenario: Groups with different dependencies share capacity
- **WHEN** an API plan selects groups with different provider dependencies
- **THEN** the planner may place them together using the same cost and resource model while retaining each atomic group and exact-once coverage

#### Scenario: A shard has a cloud dependency
- **WHEN** an assigned shard contains a group requiring cloud configuration
- **THEN** its provider steps receive the required configuration and it executes all assigned groups under the same worker and Minecraft limits, with verified owned cloud recovery

#### Scenario: Placement changes but timing semantics stay compatible
- **WHEN** previously audited api-lifecycle-v2 individual/group costs and the fixture/resource compatibility fingerprint match the current profile
- **THEN** the global planner reuses those costs, including reusable-group lifecycle floors, without reusing historical assignments or candidate receipts

### Requirement: Durable timing evidence after audited execution
The system SHALL retain per-case execution timings, fixture costs, outcomes and source identity, and publish reusable timing history only after the family's full audit succeeds. Each following run SHALL freeze the selected historical source before shard execution.

#### Scenario: A successful execution informs the next run
- **WHEN** all current selected cases, shards and cleanup pass the family's audit
- **THEN** its measured costs become available to the next comparable plan without editing repository weights
