## Purpose

Prevent newly saved templates and newly created servers from retaining an imported game port that differs from the supported container mapping, while preserving existing server workflows without a configuration migration.

## ADDED Requirements

### Requirement: Initialization configuration uses the supported game port

The system SHALL require new server configurations and saved templates to explicitly declare `SERVER_PORT=25565` for the Minecraft service and include a TCP game-port mapping whose container target is `25565`. It SHALL compare the environment value with the container target, not the published host port. A mapping with an omitted protocol SHALL be treated as TCP. The system SHALL support the existing environment map/list and short/long port forms, accept numeric and quoted numeric port values, and reject empty, null, Boolean, fractional, or unresolved game-port values. This change SHALL NOT enable arbitrary game container targets.

#### Scenario: Different host port is valid

- **WHEN** an authorized user submits a new server with `SERVER_PORT=25565` and the TCP mapping `25517:25565`
- **THEN** the initialization-port validation succeeds
- **AND** existing validation of other server settings still applies

#### Scenario: Required environment value is absent or inconsistent

- **WHEN** an authorized user submits a new server or saves a template with `SERVER_PORT` missing, invalid, or different from its supported game container target
- **THEN** the operation is rejected with an actionable validation error identifying the environment field and expected container port

#### Scenario: UDP mapping does not satisfy the game mapping

- **WHEN** the only mapping to container port `25565` explicitly uses UDP
- **THEN** initialization-port validation rejects the configuration because a TCP game mapping is required

#### Scenario: Alternate supported YAML forms

- **WHEN** equivalent configurations use an environment list with `SERVER_PORT=25565` or an environment map with `SERVER_PORT: "25565"`, and a short or long TCP port mapping
- **THEN** they receive the same initialization-port validation result

### Requirement: Initialization must permit properties-file updates

For saved templates and new server configurations, the system SHALL reject an explicitly disabled `OVERRIDE_SERVER_PROPERTIES` or enabled `SKIP_SERVER_PROPERTIES`. Omitted flags SHALL use the image defaults of enabled overriding and disabled skipping. Explicit flags SHALL use recognizable Boolean values; unresolved or invalid values SHALL be rejected instead of being assumed safe.

#### Scenario: Image defaults are sufficient

- **WHEN** a configuration has a valid game port and omits both property-management flags
- **THEN** the initialization validation succeeds

#### Scenario: Overriding is disabled

- **WHEN** a template save or new server request explicitly sets `OVERRIDE_SERVER_PROPERTIES` to false
- **THEN** the request is rejected with an explanation that an imported properties file would not be updated

#### Scenario: Property setup is skipped

- **WHEN** a template save or new server request explicitly sets `SKIP_SERVER_PROPERTIES` to true
- **THEN** the request is rejected with an explanation that property setup would be skipped

### Requirement: Template saves and final new-server submissions are validated

The system SHALL apply the initialization rules to template creation and template updates before persisting the submitted template, and to final new-server configurations in both direct and template modes before creating server files, records, or containers. Templates SHALL keep the game container target, `SERVER_PORT`, and any explicitly supplied property-management flags literal; ordinary placeholders such as host ports and memory SHALL remain supported without requiring defaults for every variable. Final new-server validation SHALL run even when a previously stored template predates the rules. Existing authentication and authorization requirements SHALL remain in effect.

#### Scenario: Template edit removes the required setting

- **WHEN** an authorized user saves an edited template that removes `SERVER_PORT`
- **THEN** the save is rejected
- **AND** the stored template remains unchanged

#### Scenario: Host-port placeholder remains available

- **WHEN** a template uses `{game_port}:25565`, declares the host-port variable without a default, and sets literal `SERVER_PORT=25565`
- **THEN** that placeholder does not prevent initialization-port validation from succeeding

#### Scenario: Critical settings cannot vary through placeholders

- **WHEN** a template uses a placeholder for `SERVER_PORT`, the game container target, or a property-management flag
- **THEN** saving the template is rejected with guidance to use a fixed value for that setting

#### Scenario: Old template is used to create a new server

- **WHEN** a new server request renders a stored template whose output omits `SERVER_PORT`
- **THEN** the new server request is rejected before server resources are created
- **AND** the template and servers previously created from it are not rewritten

#### Scenario: Direct YAML cannot bypass the rule

- **WHEN** an authorized user submits direct YAML without `SERVER_PORT` to create a server
- **THEN** the request is rejected by the same initialization rules as template-based creation

#### Scenario: Unauthorized submission

- **WHEN** a requester does not satisfy the existing authorization requirements for saving a template or creating a server
- **THEN** the operation remains denied and no configuration is persisted

### Requirement: Existing server configurations remain compatible

The system SHALL NOT require existing servers to add `SERVER_PORT` in order to remain discoverable or participate in port-conflict checks, existing configuration editing/rebuilding, template-snapshot operations, adoption, or start/stop/restart operations. This change SHALL NOT automatically edit templates, template snapshots, Compose files, or `server.properties`, nor add startup enforcement. Saving a reusable template and creating a new server SHALL still follow the new initialization rules.

#### Scenario: Legacy server remains manageable

- **WHEN** an existing server has a valid supported Compose configuration without `SERVER_PORT`
- **THEN** it remains readable and its ports remain visible to conflict checks
- **AND** this new initialization rule does not prevent editing, rebuilding, or operating that server

#### Scenario: Saved template changes do not migrate old servers

- **WHEN** an administrator adds `SERVER_PORT` to a reusable template
- **THEN** previously created servers and their template snapshots remain unchanged
