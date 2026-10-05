# DNS Provider Qualification Specification

## Purpose

Establish that managed Huawei DNS names and router mappings support real Minecraft connectivity, with independently observable convergence and recoverable test resources.

## Requirements

### Requirement: Complete and conflict-aware provider convergence
Reconciliation SHALL observe the complete provider inventory and perform compatible record replacements without treating an incomplete or failed observation as empty state. Unrelated targets SHALL continue after a target failure, and a failed replacement SHALL remain observable for a subsequent fresh reconciliation.

#### Scenario: Paginated cloud inventory
- **WHEN** the configured zone or managed records occur after the first provider page
- **THEN** reconciliation discovers them and does not create duplicate records or infer that the zone is absent

#### Scenario: Conflicting record types
- **WHEN** an address changes between a CNAME and an incompatible address record type
- **THEN** reconciliation removes the conflicting record before creating its replacement and reports any failure without hiding incomplete connectivity

### Requirement: Independently verified cloud connectivity
Selected Huawei qualification SHALL require successful deployed application tasks, known ready status, independent cloud record checks for names, types, values and TTLs, authoritative DNS answers and an initial recursive SRV observation, and a real Minecraft protocol response through the managed router.

#### Scenario: Real routing
- **WHEN** the application reconciles an owned running Minecraft server
- **THEN** a probe uses actual DNS address and service-port answers to connect to the owned mc-router using the configured game hostname to reach the expected server and verifies that server's unique response

#### Scenario: Automatic reconciliation
- **WHEN** servers are created, partially removed or synchronized, or the application restarts with DNS enabled
- **THEN** remote records and routes converge through the lifecycle trigger without an additional manual update masking a missing trigger

#### Scenario: Unknown observation
- **WHEN** either provider read fails
- **THEN** qualification cannot report success from an empty decoded difference and the failing branch preserves existing connectivity

### Requirement: Recorded cloud resources and recovery
Cloud scenarios SHALL derive relative record names from the common environment ID and an optional configured parent. They SHALL preserve unrelated records, register recovery before writes, retain non-secret domain and scope evidence outside disposable runtime directories and verify cleanup independently of application health. Recovery SHALL use the recorded domain and scope with currently supplied provider credentials.

#### Scenario: Concurrent environments
- **WHEN** multiple environments reconcile against the same configured zone
- **THEN** their record names use their respective common environment IDs and reconciliation targets remain separate

#### Scenario: Failed or interrupted run
- **WHEN** normal cleanup fails or the runner terminates unexpectedly
- **THEN** an explicit recovery operation can reclaim only recorded owned scopes using separately supplied credentials, and the original failure remains visible

#### Scenario: Configuration changes before recovery
- **WHEN** provider credentials or the configured default domain change after records are created
- **THEN** recovery uses the manifest's original domain and scope with the currently supplied provider credentials and verifies removal of managed records while preserving unrelated records

### Requirement: Candidate qualification
Provider steps SHALL receive the configuration required by their selected scenarios. The `dns-e2e` configuration store SHALL have no environment protection or branch authorization gate. Ordinary regression SHALL remain runnable without credentials. Release qualification SHALL require successful Huawei checks against the same candidate revision and image and SHALL reject missing, skipped or failed cloud evidence.

#### Scenario: Missing cloud credentials
- **WHEN** a Huawei job is selected without its configuration
- **THEN** it fails before cloud writes rather than skipping qualification

#### Scenario: Ordinary pull request regression
- **WHEN** a pull request runs the ordinary regression profile
- **THEN** its test steps are not passed cloud credentials and do not execute cloud mutations
