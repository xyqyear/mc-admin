## 1. Session-owned upload workflows

- [x] 1.1 Add the browser upload registry and authenticated global host; verify independent destinations, reopening without duplicate submission and session teardown in targeted integration tests.
- [x] 1.2 Connect existing file/archive controllers and dialogs to the registry; verify conflict decisions, cancellation, partial results and unsettled publication remain correct in targeted upload tests.

## 2. Task-center interaction

- [x] 2.1 Add upload list, active counts, retained results and clearing; verify terminal entries reopen and active work cannot be discarded by clearing completed tasks.
- [x] 2.2 Animate minimization to the actual launcher with reduced-motion and missing-API fallback; verify geometry, interaction cleanup and accessible feedback in targeted tests and browser scenarios.

## 3. Verification and delivery

- [x] 3.1 Update owning frontend documentation and public import policy; verify boundary checks and coherent lifecycle descriptions.
- [x] 3.2 Run selected upload/task-center tests, frontend lint, type checking and bundling; add browser coverage for hidden running workflows and real completion.
- [x] 3.3 Add the approved 30-second initial cloud DNS publication wait without consuming the two-minute polling budget; verify cancellation, retained retries and terminal timeout with targeted fake-clock tests.
- [ ] 3.4 Commit and push the implementation, wait for latest-SHA automatic qualification, and record its successful receipt and Actions URL.
