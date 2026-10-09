# File Directory Download Specification

## Purpose

Allow authenticated users to export selected server files into a browser-authorized directory with a complete download manifest and stable progress based on fixed byte totals.

## Requirements

### Requirement: Complete selected download manifest
The system SHALL return every selected file and directory, file byte sizes, server generation and per-entry errors in one manifest response. Parent selections SHALL subsume selected descendants, and paths SHALL remain confined to the server data directory.

#### Scenario: Complete recursive selection
- **WHEN** an authenticated user selects overlapping roots containing more than 200 entries, hidden files and empty directories
- **THEN** one response contains the complete deduplicated scope, accurate file sizes and empty directories

#### Scenario: Unsupported or inaccessible descendants
- **WHEN** a selected tree contains an escaping link, recursive directory link or unreadable entry
- **THEN** the manifest reports the entry error while retaining other readable entries and does not traverse the unsupported directory

#### Scenario: Authentication and confinement
- **WHEN** an unauthenticated client requests a manifest or a selected root escapes the server data directory
- **THEN** the request is rejected without returning an out-of-scope file

### Requirement: Fixed byte progress after scanning
The browser SHALL display a scanning phase without a percentage, obtain the complete manifest before transferring files, fix the total byte size from that manifest and update transfer progress from received bytes. Saved-file counts SHALL increase only after local writes close.

#### Scenario: A large file is still transferring
- **WHEN** part of a file has arrived while its write remains open
- **THEN** byte progress increases against the fixed total while the saved-file count does not increase

#### Scenario: Empty export contents
- **WHEN** selected contents consist only of empty files and directories
- **THEN** the browser creates the requested output and completes without dividing by zero or reporting invalid progress

### Requirement: Bounded browser transfer and partial outcomes
The browser SHALL use one queue with at most four active file transfers, retain original or flat layouts and avoid overwriting existing output. File downloads SHALL bind the manifest generation. Failures and cancellation SHALL retain already saved files and remove incomplete newly created files.

#### Scenario: A transfer finishes while another remains pending
- **WHEN** one active transfer finishes and additional files are queued
- **THEN** the browser starts the next queued file without waiting for unrelated active transfers

#### Scenario: Partial failure or cancellation
- **WHEN** a file fails or the user cancels an export
- **THEN** saved files remain, incomplete output is removed, failures are visible and cancelled work does not start subsequent transfers
