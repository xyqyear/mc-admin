## Purpose

Identify mismatches between the game port in a server's properties file and its Compose container mapping, and provide a direct route to inspect and edit the file without imposing new environment-variable requirements on existing servers.

## ADDED Requirements

### Requirement: Self-check compares file and container target only

The system SHALL expose an enabled-by-default self-check identified by `server.game_port_consistency`, with the user-facing meaning of game-port consistency. For every active server record, including stopped servers, it SHALL compare the valid `server-port` from the data-root `server.properties` with the supported TCP game container target read from that server's Compose file. It SHALL NOT compare against the host port or audit `SERVER_PORT`, property-management flags, deployed container environment/port bindings, network reachability, DNS, or firewall configuration. Its result SHALL describe configuration consistency rather than claim that players can connect.

#### Scenario: Legacy server passes without environment configuration

- **WHEN** a server has mapping `25517:25565`, file value `server-port=25565`, and no `SERVER_PORT` environment variable
- **THEN** the check reports a passed result for that server

#### Scenario: File mismatch is reported on a stopped server

- **WHEN** a stopped server has mapping `25517:25565` and file value `server-port=25566`
- **THEN** the check reports a warning associated with that server
- **AND** the evidence identifies the observed file port `25566` and expected container target `25565`

#### Scenario: Environment differences are outside this check

- **WHEN** the file port and container target both equal `25565`, but Compose contains a conflicting `SERVER_PORT` value or disables property management
- **THEN** this self-check reports that the file port and container target match
- **AND** it does not issue an environment-configuration warning

### Requirement: Uninitialized and starting states avoid premature findings

The check SHALL report an informational skipped result when a non-running server has no `server.properties`, and SHALL defer file comparison while the server is reported as starting. It SHALL NOT wait indefinitely for startup or mark skipped comparisons as passed. A later manual, scheduled, or existing event-triggered run SHALL evaluate the current state again without requiring a new trigger mechanism.

#### Scenario: Properties have not been generated

- **WHEN** a non-running server has no data-root `server.properties`
- **THEN** the result explains that the file has not been generated and comparison was skipped

#### Scenario: Startup can still replace an imported value

- **WHEN** a server is reported as starting while its file contains a different port
- **THEN** the check reports an informational skipped result instead of a mismatch warning
- **AND** a later run compares the file when the server is no longer starting

### Requirement: Invalid inputs remain visible and isolated

For a server that is not in a deferred state, the check SHALL report a server-specific failed result with warning severity when the Compose target or properties port cannot be determined reliably. This includes unreadable or malformed files, a missing or invalid `server-port` in an existing file, an unavailable supported TCP game mapping, and a missing properties file on a running server. Failures SHALL NOT prevent checking other servers. Evidence SHALL contain relevant port/path/error information rather than complete configuration files or unrelated environment values.

#### Scenario: Invalid file does not hide another server's mismatch

- **WHEN** one server's file is unreadable and another server has a valid but mismatched file port
- **THEN** the first server receives a failed finding and the second receives its mismatch warning
- **AND** neither result claims that comparison passed for the unreadable file

#### Scenario: Running server unexpectedly lacks its properties file

- **WHEN** a server is running outside the starting state and its properties file is missing
- **THEN** the check reports a failed finding rather than treating it as an uninitialized server

### Requirement: Findings reuse existing self-check controls and history

The new check SHALL participate in the existing catalog, per-check enable/disable configuration, manual full and single-check runs, scheduled runs, current-state projection, event-triggered full runs, and retained history. Disabling it SHALL remove its contribution to current warning counts while preserving historical results. Running the check or rerunning a finding SHALL NOT change server configuration or lifecycle state.

#### Scenario: Manual rerun observes a correction

- **WHEN** a user corrects a mismatched file through the existing editor and reruns the check
- **THEN** the new result compares the current file and updates the displayed current state
- **AND** the previous warning remains in retained history

#### Scenario: Existing stored configuration lacks the new toggle

- **WHEN** self-check settings written before this feature are loaded
- **THEN** the new check is enabled by default without requiring a configuration migration

#### Scenario: Disabled check is excluded from current problems

- **WHEN** the new check is disabled through the existing self-check configuration
- **THEN** its findings no longer contribute to the current warning count
- **AND** its retained historical findings remain available

### Requirement: Remediation locates the editable file

For a mismatch or file-related failed finding associated with a server, the self-check interface SHALL provide a link in its remediation area to that server's data-root file browser, with the search input and active literal search already set to `server.properties`. The link SHALL work in current and retained findings, preserve normal authentication and file-access rules, and only navigate; it SHALL NOT automatically edit, save, or restart anything. Reloading the destination SHALL preserve the directory and search.

#### Scenario: User opens the affected file location

- **WHEN** an authorized user follows the remediation link for server `survival`
- **THEN** the file browser opens for `survival` at its data root
- **AND** the search box contains `server.properties` with regex mode disabled and matching files displayed
- **AND** the user can open the file using the existing editor interaction

#### Scenario: Link cannot grant file access

- **WHEN** a requester without the required access follows a remediation URL
- **THEN** the existing authentication and file-access restrictions continue to apply

### Requirement: Remediation explains file edits and possible overrides

Mismatch findings SHALL advise setting `server-port` to the reported container target and restarting the server after saving. They SHALL also provide static guidance that an explicit conflicting `SERVER_PORT` can overwrite the file on startup, in which case the Compose configuration must be corrected and the container recreated through the existing workflow. This guidance SHALL NOT require inspecting environment variables as part of the self-check.

#### Scenario: Correction guidance remains useful for legacy and managed properties

- **WHEN** a mismatch finding is displayed
- **THEN** its remediation identifies the expected file value and the need to restart after a file edit
- **AND** explains the conditional Compose override and container-recreation case without asserting that such an override was detected
