## 1. Session-owned upload workflows

- [x] 1.1 Add the browser upload registry and authenticated global host; verify independent destinations, reopening without duplicate submission and session teardown in targeted integration tests.
- [x] 1.2 Connect existing file/archive controllers and dialogs to the registry; verify conflict decisions, cancellation, partial results and unsettled publication remain correct in targeted upload tests.

## 2. Task-center interaction

- [x] 2.1 Add upload list, active counts, retained results and clearing; verify terminal entries reopen and active work cannot be discarded by clearing completed tasks.
- [x] 2.2 Animate minimization to the actual launcher with reduced-motion and missing-API fallback; verify geometry, interaction cleanup and accessible feedback in targeted tests and browser scenarios.
- [x] 2.3 Combine each upload entry into one clickable progress heading with an adjacent upload icon; retain terminal filenames and destination tooltips, and verify reopening without duplicate filename/origin rows.
- [x] 2.4 Reproduce the overlapping original popup during minimization, hide it from the first animation frame in both upload workflows, and verify visible animation copies plus reduced-motion behavior in real browsers.

## 3. Verification and delivery

- [x] 3.1 Update owning frontend documentation and public import policy; verify boundary checks and coherent lifecycle descriptions.
- [x] 3.2 Run selected upload/task-center tests, frontend lint, type checking and bundling; add browser coverage for hidden running workflows and real completion.
- [x] 3.3 Commit and push the implementation, wait for latest-SHA automatic qualification, and record its successful receipt and Actions URL.

## Verification evidence

- Chrome reproduction confirmed the real popup remained visible during its exit animation while the minimizing copy moved. Popup `display: none` bypasses both exit painting and visibility transitions.
- Targeted Vitest coverage: 13 tests across upload list, animation and authenticated-host integration; lint, type checking, boundary checks and bundling passed. Filename coverage includes files selected after opening, later batch items and numeric ordinary-file names.
- Real browser upload cases: ordinary file, archive with motion, and archive with reduced motion all passed against image `sha256:99140b6e24cdc0257db7e1df043a831de1d76ff8c9f673707ee212f078ee72ab`; owned run `browser-531a69b8dc32` verified cleanup. Both animated cases assert the original is invisible and the copy visible in its first frame, then independently verify downloaded bytes. Each heading contains its filename exactly once.
- Complete qualification: [Actions run 42261782592](https://github.com/xyqyear/mc-admin/actions/runs/42261782592) executed candidate, static, backend, API and browser gates successfully for `bf41400b83270ec3366bf48a50289d3c6b59b172`. The audited totals are 103 API cases and 27 browser cases across three browser shards, with both cloud scopes cleaned.
- Verified receipt: `application-qualification-4314e924a0918fbe287c19477ea2fd3f03e56c21d51d9541d86b14fb549b27d6`, mode `full`, final image `sha256:bc1379153727e5342af52fb638cee09a381004e5f6b2ef639f216aa75711f020`. Source, content fingerprint and candidate identities passed the repository's receipt validator.
