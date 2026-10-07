## 1. Scoped backend file operations

- [x] 1.1 Add bounded authenticated recursive download manifests and path-confinement behavior tests.
- [x] 1.2 Add one durable batch deletion command with full preflight, resource reservations, truthful per-target results and cancellation tests.
- [x] 1.3 Extend compression to disjoint multi-path data scopes preserving paths and empty directories, with atomic publication and targeted tests.

## 2. Snapshot metadata and source eligibility

- [x] 2.1 Persist editable notes by real repository and full snapshot identity with an additive migration and restart/identity tests.
- [x] 2.2 Project notes through creation, lists and eligible sources; preserve created snapshots when note saving fails; unify file source eligibility with recovery protection.
- [x] 2.3 Add shared creation note input, note editing and note display to snapshot lists and recovery selectors with integration tests.

## 3. Browser direct export

- [x] 3.1 Add capability/environment detection and streaming file/folder export with bounded concurrency and safe flat/original path mapping.
- [x] 3.2 Track aggregate file/byte progress, failures, cancellation and filename mappings through browser download tasks, with focused stream tests.

## 4. Feature entrypoints

- [x] 4.1 Open existing player details in place from overview cards, independently of online-list updates, with interaction coverage.
- [x] 4.2 Add shared batch actions, identity-safe selection and advanced-search real-result checkboxes with correct captured path roots.
- [x] 4.3 Connect multi-path snapshot/recovery, batch deletion, packing and file/folder direct download; show unavailable controls and version-free tooltips; cover navigation and partial results.

## 5. Verification and delivery

- [x] 5.1 Extend real API E2E and browser journeys for batch scope, archive contents, notes, overview details and direct-download capability/outputs; update coverage evidence.
- [x] 5.2 Update current-state feature design docs and applicable AGENTS guidance; validate OpenSpec artifacts.
- [x] 5.3 Run directly affected local tests plus required frontend/backend/Go static checks and frontend build.
- [x] 5.4 Prepare the reviewable implementation on the development branch with conventional issue-linked commit contents.

## 6. Restoration observation and stable file controls

- [x] 6.1 Share one adaptive active-restoration polling observer per client/server across file, world and history views, with fresh entry/re-enable checks and truthful recovery guards.
- [x] 6.2 Refresh restoration history on entry, actions and invalidation without periodic Restic reads; verify idle, active, errors, lifecycle and multi-consumer behavior with focused tests.
- [x] 6.3 Keep batch control geometry stable across selection and ignore-check states in browsing and advanced search, retaining reasons in button tooltips and browser layout coverage.
- [x] 6.4 Update current-state observation/file documentation, validate specifications, run affected tests and required frontend checks, and prepare issue-linked commits on the follow-up branch.

## 7. Browser-local export names

- [x] 7.1 Use one filesystem-safe browser-local timestamp format for archive commands and export folders, retaining existing directory collision protection and covering exact output names.
- [x] 7.2 Accept validated client timestamps for archive naming, omit path and random identifiers, preserve independent outputs and prevent publication from overwriting a late collision.
- [x] 7.3 Cover non-UTC browser naming and repeated archive timestamps through real browser/API scenarios, update contracts and current-state documentation, and complete affected verification and issue-linked commits.

Delivery requires pushing the development branch and qualifying its latest SHA with `publish=false`, then verifying every required gate and coverage/cleanup audit under the root AGENTS.md workflow. This external gate remains required after the versioned implementation checklist is complete.
