## Purpose

Provide direct editing of typed template variable definitions and values across template authoring, server creation and server configuration, preserving constraints, snapshot identity and explicitly authored drafts.

## ADDED Requirements

### Requirement: Typed template values
The application SHALL render and validate string, integer, number, enum and boolean template values from their variable definitions. Defaults SHALL initialize missing values without replacing authored values. False and zero SHALL remain valid values when permitted by their definitions.

#### Scenario: Create a server from a template
- **WHEN** a user selects a template and supplies values within its constraints
- **THEN** preview and creation receive those typed values
- **AND** missing or invalid required values prevent creation

### Requirement: Variable definition authoring
Users SHALL edit type-specific constraints and defaults with ordinary form controls. Invalid definitions SHALL be rejected while retaining the authored input.

#### Scenario: Invalid enum default
- **WHEN** an enum default is absent from its options
- **THEN** confirmation is blocked and the editor explains the error

### Requirement: Existing server snapshot identity
Existing-server edits SHALL use the server's captured variable definitions even if the source template changes or is deleted. Configuration writes and conversions SHALL preserve accepted-version conflict handling and authored values.

#### Scenario: Source template changes
- **WHEN** a source template changes while an existing server's values are edited
- **THEN** the editor retains its captured definitions and authored values until explicit template conversion
