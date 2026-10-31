## MODIFIED Requirements

### Requirement: Complete automated API selection
Every freshly executed pull request regression, automatic CI and complete qualification SHALL execute every case in the current API catalog except DNSPod. The shared coordinator SHALL accept historical complete execution only under the content-qualification contract. The CI profile menu SHALL contain only `regression`, `qualification` and `dnspod`; DNSPod SHALL require explicit selection. Local case and tag filters SHALL remain available for related validation.

#### Scenario: A current case joins automated regression
- **WHEN** a non-DNSPod case is registered in the current catalog
- **THEN** both regression and qualification require it without a separate opt-in or historical timing entry

#### Scenario: DNSPod is not explicitly selected
- **WHEN** a pull request, automatic CI or complete qualification runs the default API inventory
- **THEN** DNSPod is excluded and all other current cases remain required
