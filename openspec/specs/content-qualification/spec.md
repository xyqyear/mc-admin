# Content Qualification Specification

## Purpose

Avoid repeated complete validation of unchanged application content while retaining trustworthy release evidence, current version information and immutable publication.

## Requirements

### Requirement: Content-equivalent qualification
Qualification SHALL identify effective application, test, dependency, build and verification inputs independently of commit identity. Only explicitly designated documentation and release data SHALL be excluded from complete-test identity. Unknown inputs SHALL invalidate reuse. Release data SHALL participate in final artifact identity.

#### Scenario: Documentation or merge changes the commit
- **WHEN** a new commit has identical effective inputs and release data
- **THEN** it reuses verified qualification and the original image digest while retaining both source identities

#### Scenario: A test fixture or workflow changes
- **WHEN** any test, fixture, dependency, workflow or unknown input changes
- **THEN** prior qualification for different effective content cannot qualify the commit

### Requirement: Trusted bounded evidence
Reuse SHALL require complete successful qualification from the trusted coordinator in the same repository, matching content and immutable artifact identities, successful coverage and cleanup, and an unexpired original verification time. PR/fork, failed, cancelled, partial or corrupted evidence SHALL NOT authorize publication. Missing or expired evidence SHALL cause full validation. Forced validation SHALL bypass reuse. Reuse SHALL NOT refresh original verification age.

#### Scenario: Candidate expired before release
- **WHEN** a receipt exists but its required candidate is unavailable
- **THEN** complete validation produces a new candidate before publication

#### Scenario: Evidence is incomplete or mismatched
- **WHEN** a receipt or archive does not match its trusted run, source, required gates or digest
- **THEN** publication is rejected

### Requirement: Bounded release-data derivation
Release-data-only changes SHALL preserve all tested application layers and runtime configuration. The final image SHALL contain the new validated release data and pass actual-image startup and notification checks before qualification. Every derived receipt SHALL identify the original complete qualification and its final checked image.

#### Scenario: Only release notes change
- **WHEN** release data changes but effective code remains qualified
- **THEN** only data validation and bounded final-image checks execute, and the published UI shows the new version notes

#### Scenario: Derivation changes executable content
- **WHEN** a proposed metadata derivation changes another file or runtime setting
- **THEN** it is rejected and cannot inherit qualification

### Requirement: Unified validation and immutable publication
Automatic, manual and tag qualification SHALL share a content-based decision path. Equivalent concurrent requests SHALL serialize qualification and recheck available evidence. Tag publication SHALL copy an already qualified final image without rebuilding it. Each target SHALL expose whether evidence was executed or reused and its source run.

#### Scenario: A tag follows successful validation
- **WHEN** the same release content already has available qualified artifacts
- **THEN** tag publication reuses that evidence and copies its exact final digest without rerunning complete tests

### Requirement: Local version data loading
The UI SHALL read validated version data from its deployed application's static resources, preserve SemVer notification and local acknowledgment behavior, and not reuse stale HTTP-cached data after upgrade. Loading failures SHALL be recoverable and SHALL NOT acknowledge an unknown version.

#### Scenario: Release data is temporarily unavailable
- **WHEN** version data cannot be loaded or validated
- **THEN** application navigation remains available, version acknowledgment is unchanged, and the version dialog offers retry
