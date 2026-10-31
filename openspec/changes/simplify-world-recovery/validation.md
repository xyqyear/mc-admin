# Validation evidence

Issue: #183. Development branch: `refactor/world-recovery-no-exclusions`.
No production deployment or release is part of this change.

## Candidate computation

Measured on 2026-10-31 with 385 snapshots, three samples per cell, reporting
median wall time in seconds. Both versions use identical source roots and
selected terrain/entities/POI MCA paths. The historical `protected` input
excludes the entire entities directory; `distinct` varies exclusions outside
the world. The comparison changes only the expected skip semantics to zero.

| Regions | Shared rules, before / after | Distinct rules, before / after | Entities excluded, before / after |
| --- | --- | --- | --- |
| 6 | 0.002805 / 0.003427 | 0.109188 / 0.002013 | 0.107716 / 0.002042 |
| 24 | 0.003264 / 0.002168 | 0.225443 / 0.002205 | 0.504636 / 0.002192 |
| 96 | 0.005013 / 0.003018 | 0.728563 / 0.002785 | 2.517965 / 0.002982 |
| 384 | 0.012026 / 0.005148 | 2.581941 / 0.005701 | 11.494631 / 0.006472 |

The 384-region broad-exclusion case's maximum scheduler gap fell from 3.698 s
to 0.0111 s with a 10 ms observer. These measurements exclude Restic metadata
reads and scope/path preparation and do not predict total UI latency.

The committed responsiveness test also defeats source-root reuse with 385
distinct root sets: 384 regions completed in 1.588 s, maximum scheduler gap
0.0143 s. Coverage work can still scale with distinct source roots and selected
regions. Exclusions no longer create per-region MCC skip expansion.

## Local checks

- Backend regression checks use real Restic, fd and mcmap for world selection,
  source absence, previews, safety snapshots and repeated rollback. File
  exclusions, cancellation and path ownership retain independent assertions.
- Frontend target/source/restore/history tests: 24 unique tests across five files.
- Pyright, Ruff, frontend TypeScript, ESLint, import boundaries, generated
  identity contracts and production bundle passed.
- Go world package vet and E2E runner build passed. The application image
  `mc-admin:world-no-exclusions` is local test output only.
- OpenSpec change and current specifications validated.

The deployed `world.snapshot-query-responsiveness` case passed normally
(`e2e-4e36b3f150a8`, 85.1 s) and with `--no-reuse`
(`e2e-1ebe7fa82ee0`, 73.9 s), including owned teardown. Both used local image
`sha256:579065a99e6d8f3b76cd6713b8308dbd0b5820fda4d9a2e2508c1ae8ebd6a613`.
The scenario asserts 384-region read responsiveness, authentication, ordinary
backup exclusions, world snapshot completeness, negative-coordinate MCA/MCC
bytes, deletion of historically excluded data and exact safety rollback.

Backend verification passed 97 unique selected tests (46 world/eligibility tests, 47 file/world/HTTP cleanup tests, three architecture checks and one reviewed API contract check). The six performance nodes were also run with timing output. Qualification is pending.
