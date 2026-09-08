## Purpose

Provide independently runnable real API regression scenarios for all backend feature families, with observable assertions, operation coverage accounting and explicit external dependency qualification.

## ADDED Requirements

### Requirement: Complete functional domain coverage
The regression catalog SHALL include functional scenarios for every shipped backend feature family and document each exposed operation's scenario coverage. Discovery or authorization-only requests SHALL NOT be represented as full feature verification.

#### Scenario: Execute a feature regression
- **WHEN** a supported feature is selected with its required real dependencies
- **THEN** its scenario verifies relevant success effects, representative rejection paths and asynchronous completion through the deployed application

#### Scenario: Verify task-center access boundaries
- **WHEN** task-center operations are exercised without authentication, with an invalid session, or with a valid session missing CSRF protection on mutations
- **THEN** requests are rejected without changing existing task state, and authenticated requests with the required protection retain their supported behavior

#### Scenario: Verify login credential handling
- **WHEN** a real browser login-code flow confirms a code and consumes its completion ticket using default audit configuration
- **THEN** neither credential value appears in operation audit or ordinary application logs, and public task and status fields remain observable

#### Scenario: Account for the API surface
- **WHEN** a backend operation is introduced or a qualification run completes
- **THEN** coverage accounting identifies the operation and distinguishes exercised scenarios from missing or unexecuted coverage

#### Scenario: Report health with valid Docker labels
- **WHEN** a real Minecraft container has a label value containing equals signs
- **THEN** Docker and Compose output remains readable and the deployed lifecycle API reports the container's healthy state

#### Scenario: Reject an unobserved operation in full regression CI
- **WHEN** the full regression CI audit finds a deployed HTTP or WebSocket operation with no scenario observation
- **THEN** the observation gate fails and identifies the missing operation without treating rejection-only observations as successful feature behavior

### Requirement: Explicit external qualification
External-provider scenarios SHALL declare their required credentials and disposable resource scope, use the real external provider, and fail visibly when selected without required configuration. Local regression selection SHALL be independently runnable without cloud credentials.

#### Scenario: Missing DNS qualification input
- **WHEN** a DNS provider scenario is selected without its required test-domain credentials
- **THEN** it fails with an actionable dependency error instead of passing or silently skipping

#### Scenario: Reclaim test DNS records
- **WHEN** a provider scenario completes or fails after creating records
- **THEN** it attempts to remove only records in its unique authorized test namespace and preserves any cleanup failure

### Requirement: Independent reproducible scenarios
Regression scenarios SHALL retain owned mutable state, bounded execution, failure evidence and cleanup, and SHALL remain runnable individually and without environment reuse.

#### Scenario: Concurrent regression shards
- **WHEN** shards run concurrently on a shared supported Docker host
- **THEN** scenarios operate only on their owned application, data and resource namespaces and report their individual outcomes

### Requirement: Honest defect handling
The qualification process SHALL preserve assertion failures and SHALL NOT count unexpected server errors, mocked dependencies or incomplete stream/task results as successful feature tests.

#### Scenario: Regression exposes a product defect
- **WHEN** a real scenario contradicts the documented feature contract
- **THEN** the defect is fixed with regression evidence or remains explicitly reported as a failing limitation
