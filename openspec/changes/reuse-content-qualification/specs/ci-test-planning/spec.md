## MODIFIED Requirements

### Requirement: Integrated provider execution
API E2E SHALL own external-provider scenarios, their costs, execution plans and aggregate audits. Every newly executed complete regression or qualification SHALL require every current API case except DNSPod and verified owned cloud cleanup. The shared qualification coordinator SHALL permit reuse only under the content-qualification contract. Provider dependency metadata SHALL select required private configuration and recovery steps. Every API shard SHALL use `dns-e2e` as an unrestricted configuration store with no environment protection or branch authorization gate, and provider steps SHALL receive credentials only when required.

#### Scenario: Automated API validation omits a required case
- **WHEN** newly executed regression or qualification requires a current non-DNSPod scenario but its assigned execution is absent, skipped or failed
- **THEN** the API aggregate gate fails

#### Scenario: A pull request executes ordinary regression
- **WHEN** a pull request executes fresh validation through the shared coordinator
- **THEN** its plan includes every current non-DNSPod case and provider steps receive the configuration and credentials required by their assigned cases

#### Scenario: Docker cleanup succeeds but cloud records remain
- **WHEN** owned local containers are removed while a selected cloud scope lacks verified cloud cleanup
- **THEN** API qualification fails and retains the non-secret recovery evidence
