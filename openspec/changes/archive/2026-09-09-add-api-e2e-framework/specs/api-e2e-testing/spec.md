## Purpose

Provide reproducible API smoke tests of deployed MC Admin instances with real dependencies, isolated concurrent runs, and actionable failure evidence.

## ADDED Requirements

### Requirement: Independent execution against real deployments
The test tool SHALL run as a separately built executable and exercise the application over its public network APIs, including real application startup, persistent storage, Minecraft containers, and Restic for scenarios requiring those resources.

#### Scenario: Run the smoke suite
- **WHEN** an operator supplies an application image on a supported Linux Docker host
- **THEN** the tool provisions the required environments, runs the selected scenarios, reports their outcomes, and exits unsuccessfully if any scenario or required cleanup fails

#### Scenario: Missing dependency
- **WHEN** a selected scenario cannot be provisioned because a dependency is unavailable
- **THEN** the tool reports a setup error and does not count that scenario as passing or silently skipped

### Requirement: Explicit environment isolation and reuse
Every scenario SHALL declare its environment and reuse policy. Fresh environments SHALL have independent mutable application state. Reused environments SHALL be exclusively leased and verified before subsequent use; failed or unverified environments SHALL be discarded.

#### Scenario: Destructive scenario
- **WHEN** a scenario changes global configuration or restores data with fresh isolation
- **THEN** subsequent scenarios receive their declared initial state independently of those changes

#### Scenario: Failed reusable environment
- **WHEN** a reusable scenario, its cleanup, or its environment verification fails
- **THEN** the environment is retired and the failure remains visible in the run result

### Requirement: Deterministic parallel execution
The tool SHALL list and select stable scenario identifiers, partition them deterministically across CI shards, limit worker and Minecraft concurrency, and support disabling reuse and recording execution order.

#### Scenario: Multiple concurrent runs
- **WHEN** two runs execute against the same local Docker daemon
- **THEN** their application data, container identities, Compose projects, and allocated ports do not intentionally overlap and cleanup is restricted to each run's resources

#### Scenario: Partition a suite
- **WHEN** all shards execute the same selection and shard count
- **THEN** every selected scenario belongs to exactly one shard

### Requirement: Owned-resource recovery and diagnostics
The tool SHALL retain machine-readable results, JUnit reports, redacted request evidence, and dependency logs. Cleanup SHALL support retry after interruption and SHALL validate ownership before deleting Docker resources or runtime directories.

#### Scenario: Interrupted execution
- **WHEN** execution is cancelled or a prior run leaves resources behind
- **THEN** an explicit cleanup operation can reclaim the recorded owned resources without pruning unrelated Docker resources

#### Scenario: Assertion failure
- **WHEN** an API assertion or asynchronous completion check fails
- **THEN** the report preserves the failing step, distinguishes the failure phase, and does not automatically turn it into a pass by retrying the scenario

### Requirement: Extensible smoke coverage
The project SHALL document its backend feature inventory and provide independent smoke scenarios spanning authentication and authorization, configuration persistence, template and server management, files and archives, asynchronous tasks, Minecraft lifecycle, and snapshot restoration.

#### Scenario: Add a feature test
- **WHEN** a developer adds a scenario using existing environment capabilities
- **THEN** it can be registered in its domain suite without changing the environment scheduler or adding a CI matrix entry for its directory
