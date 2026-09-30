## Purpose

Establish that managed Huawei DNS names and router mappings support real Minecraft connectivity, with independently observable convergence and recoverable test resources.

## ADDED Requirements

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

### Requirement: Bounded cloud ownership and recovery
Cloud scenarios SHALL authorize a fixed parent namespace and allocate a unique descendant per environment. They SHALL preserve unrelated records, register recovery before writes, retain non-secret ownership evidence outside disposable runtime directories and verify cleanup independently of application health.

#### Scenario: Scope collision
- **WHEN** a proposed environment scope already contains records
- **THEN** setup refuses to modify or delete those records

#### Scenario: Failed or interrupted run
- **WHEN** normal cleanup fails or the runner terminates unexpectedly
- **THEN** an explicit recovery operation can reclaim only recorded owned scopes using separately supplied credentials, and the original failure remains visible

### Requirement: Trusted candidate qualification
Cloud credentials SHALL be available only to trusted cloud jobs. Ordinary regression SHALL remain runnable without credentials. Release qualification SHALL require successful Huawei checks against the same candidate revision and image and SHALL reject missing, skipped or failed cloud evidence.

#### Scenario: Missing cloud credentials
- **WHEN** a trusted Huawei job is selected without its configuration
- **THEN** it fails before cloud writes rather than skipping qualification

#### Scenario: Untrusted pull request
- **WHEN** an untrusted contribution runs ordinary regression
- **THEN** it receives no cloud credential and does not execute cloud mutations
