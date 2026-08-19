## 1. Backend Weekday Normalization

- [x] 1.1 Add a conventional-crontab weekday parser that expands numeric values, case-insensitive names, lists, ascending ranges, wildcard steps, and ranged steps into a deduplicated calendar-day set, preserving bare `*` and rejecting malformed or out-of-range input.
- [x] 1.2 Translate the expanded set into a deterministic APScheduler 3 Monday-zero list, including both Sunday aliases, and apply it only to the fifth field passed from the shared cron trigger builder.
- [x] 1.3 Preserve validation-before-mutation behavior so an invalid weekday expression cannot create or replace a persisted or active schedule.

## 2. Backend Verification

- [x] 2.1 Add focused unit tests for `0`, `7`, `1`, `6`, case-insensitive names, named ranges, `1-5`, `0-2`, `*/2`, ranged steps, mixed lists, duplicate Sunday aliases, and deterministic output.
- [x] 2.2 Add validation tests for malformed terms, value `8`, descending ranges, and non-positive steps, including protection of an existing active schedule during a rejected update.
- [x] 2.3 Add scheduler integration tests using fixed datetimes to prove conventional Monday and Sunday execution and compound-expression calendar-day sets.
- [x] 2.4 Add lifecycle tests proving create, update, resume, system-job submission, and startup recovery share normalization while database/API expressions remain unchanged.

## 3. User Contract And Documentation

- [x] 3.1 Correct raw-mode frontend guidance to document weekday values `0-7`, with `0` and `7` as Sunday, while keeping the existing conventional selector and display mappings.
- [x] 3.2 Update `backend/docs/cron.md` and `frontend-react/docs/cron-management.md` with the conventional weekday contract and scheduler-boundary normalization behavior.
- [x] 3.3 Add a release compatibility note warning operators that numeric expressions manually compensated for APScheduler 3 numbering require review; named weekdays are unaffected.

## 4. Final Validation

- [x] 4.1 Run the focused backend cron test suite and the broader non-Docker backend test selection affected by cron lifecycle behavior.
- [x] 4.2 Run backend Pyright diagnostics.
- [x] 4.3 Run frontend lint and production build checks.
- [x] 4.4 Validate the OpenSpec change in strict mode and confirm every requirement scenario is covered by an implementation test or explicit verification.
