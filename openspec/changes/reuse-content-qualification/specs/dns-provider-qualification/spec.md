## MODIFIED Requirements

### Requirement: Candidate qualification
Provider steps SHALL receive the configuration required by their selected scenarios. The `dns-e2e` configuration store SHALL have no environment protection or branch authorization gate. Fresh pull request regression, automatic CI and release qualification SHALL require every current API case except DNSPod against the same candidate revision and image and SHALL reject missing, skipped or failed cloud evidence. Inherited qualification SHALL satisfy the content-qualification contract, including original successful cloud execution and verified cleanup. DNSPod SHALL run only when explicitly selected; local scenarios without cloud dependencies SHALL remain runnable without cloud credentials.

#### Scenario: Missing cloud credentials
- **WHEN** a Huawei job is selected without its configuration
- **THEN** it fails before cloud writes rather than skipping qualification

#### Scenario: Ordinary pull request regression
- **WHEN** a pull request runs the ordinary regression profile
- **THEN** required cloud scenarios execute with their configured credentials, verify owned resource cleanup and fail if either execution or cleanup is incomplete
