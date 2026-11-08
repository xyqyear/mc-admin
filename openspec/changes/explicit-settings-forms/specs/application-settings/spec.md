## Purpose

Provide dedicated application settings pages and typed configuration resources so administrators can edit runtime behavior with suitable controls while preserving stored values, validation and immediate runtime updates.

## ADDED Requirements

### Requirement: Dedicated settings resources
The application SHALL expose authenticated read, replace and reset operations for DNS, snapshots, log parsing, players, map rendering, world and self-check settings. Each resource SHALL declare its complete data contract and return the effective saved settings.

#### Scenario: Save and reload settings
- **WHEN** an authenticated user replaces valid world settings
- **THEN** the response and subsequent read contain the saved values
- **AND** the runtime observes the committed settings

#### Scenario: Invalid or unauthorized write
- **WHEN** settings fail structural or domain validation, or the caller is unauthenticated
- **THEN** the request is rejected and stored and runtime settings remain unchanged

#### Scenario: Reset a resource
- **WHEN** a user confirms resetting one settings resource
- **THEN** that resource returns to current defaults and unrelated resources remain unchanged

### Requirement: Settings navigation and authored drafts
The sidebar SHALL provide a dedicated link for each settings page. Pages SHALL support grouped fields, text editors, lists and maps appropriate to their data. Failed reads SHALL offer retry without establishing an empty writable configuration. Failed writes and background reads SHALL preserve authored drafts. Explicit reload SHALL discard a draft only after a successful read.

#### Scenario: Open an editor directly
- **WHEN** a user opens the log-parser settings URL
- **THEN** the sidebar selects its submenu and the page displays the saved rules in editable text controls

#### Scenario: Save fails after authoring
- **WHEN** a user changes a rule and saving fails
- **THEN** the authored rule remains available for correction and retry

### Requirement: Stored configuration continuity
Application upgrades SHALL preserve explicitly stored values and retain the existing validation and migration boundaries for repairable legacy configuration.

#### Scenario: Upgrade with custom parser patterns
- **WHEN** an existing database is loaded by the new application
- **THEN** custom rules and configured values remain intact and editable

### Requirement: Scheduled job parameter contracts
Scheduled jobs SHALL associate each supported task identifier with its concrete parameter contract. Switching task type SHALL initialize the new type without retaining parameters from the previous type. Parameter editing and helper controls SHALL require explicit task saving.

#### Scenario: Edit backup and restart parameters
- **WHEN** a user switches from backup to restart
- **THEN** the form displays the restart target and does not submit backup retention fields
- **AND** pressing Enter in the parameter editor does not save the task
