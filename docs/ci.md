# CI scheduling and timing evidence

The release qualification graph builds one immutable candidate while static checks and backend tests run independently. API and browser shards consume the same candidate. Complete API qualification includes Huawei DNS/Minecraft scenarios and verified cloud recovery. See [release qualification](release.md) for source and image identity checks.

## Scheduling budget

Backend, API and browser planners target 300 seconds of execution per shard, including fixture initialization and cleanup. Checkout, dependency installation, OCI/Chromium preparation and runner queueing are reported separately. The target is not a deadline: test assertions, propagation waits and independent cleanup budgets retain their contracts. Plans create additional shards when predicted execution exceeds the target, within explicit shard/concurrency limits. Oversized indivisible units and fixed overhead are reported rather than truncated or retried.

Backend runners execute pytest sequentially without worker processes sharing Docker fixtures. Planning retains whole files and shared-fixture groups, assigns longest-cost units first and derives capabilities from selected tests. Actual setup/call/teardown costs are aggregated from current node identities; unseen tests receive positive fallback estimates. Exact node-ID and execution-phase audits remain mandatory before combined coverage and timing publication.

API planning globally allocates every atomic group selected by a profile into one immutable plan and one matrix. Fresh cases and reusable recipe groups remain intact; ordinary and Huawei groups may share a shard. The matrix permits at most 16 shards and eight concurrent jobs, with two workers and one Minecraft slot per runner. Provider requirements supply dependency metadata and credential/recovery bindings. Qualification currently requires 85 cases including every Huawei scenario; ordinary PR regression selects 83 cases without cloud credentials, and DNSPod/Mojang remain explicit profiles. Capacity and ownership remain held through teardown; seed changes execution priority. See [API execution contracts](../e2e/docs/architecture.md).

Browser planning uses explicit stable case identities and verified isolation boundaries. Every shard gets an independent owned application/world and one Playwright worker. Each estimate includes repeated wrapper setup and cleanup plus case execution; the wrapper and Playwright reports are audited together. See [browser execution](../frontend-react/docs/browser-tests.md).

Shard counts and simultaneous runner counts are separate budgets. A larger matrix can execute in waves; preparation, candidate construction and account-wide availability still affect overall elapsed time. Job creation-to-start intervals include dependencies and matrix constraints and do not directly measure account quota exhaustion.

Standalone ordinary push/PR runs use component-specific concurrency groups and cancel superseded executions. Protected cloud qualification, manual runs and reusable qualification children use run identities so a later branch push cannot cancel cloud recovery or their caller. Release promotion remains serialized and non-cancelling. Candidate artifacts and qualification receipts are never reused across unrelated runs.

## Historical feedback

`scripts/ci/timing_history.py` restores a read-only historical artifact once during family planning. It prefers the latest compatible successfully audited sample on the current branch, then trusted main. The envelope identifies its family, execution profile, measurement/configuration fingerprint and source run, attempt, commit and branch. Compatibility covers fixture/resource/measurement configuration and pinned inputs, not the source SHA, so costs can inform later commits. Expired, malformed, incompatible or absent history uses explicit positive fallback estimates.

Planning freezes the restored snapshot and its identity before generating the current immutable plan. Every shard executes that plan; independent shards never each choose a different latest history. History affects costs and placement only. The current collected catalog and execution policy independently determine completeness and required protected scenarios.

API history retains api-lifecycle-v2 individual costs, reusable-group membership/floors and fixed cleanup/recovery overhead. Global matrix placement preserves that measurement and compatibility fingerprint, so matching prior audited costs remain reusable. Historical assignments and candidate receipts are never reused.

Each family publishes `timing-history-<family>` only after its complete successful coverage, outcomes, candidate/cleanup audit. History artifacts retain `history.json` for 90 days; raw failed reports remain diagnostic and cannot replace successful costs. New and changed inventories remain fully selected, with unseen identities receiving fallback estimates. Read-only Actions permissions allow cross-run retrieval without repository writes or automatic weight commits.

## Evidence

| Artifact | Evidence |
| --- | --- |
| `backend-test-inventory` | Full inventory and deterministic shard plan |
| `backend-test-shard-N` | Selection manifest, precise setup/call/teardown timings, JUnit and raw coverage |
| `backend-test-reports` | Audited shard evidence and centrally combined coverage reports |
| `frontend-test-results` | Vitest JSON with individual test outcomes and durations |
| `go-test-results` | Race-enabled Go test JSON events, including per-test and package elapsed times |
| `api-results-N` | API plan, provider dependencies, lifecycle timings, outcomes, candidate identity and redacted diagnostics; cloud-dependent shards retain DNS/Minecraft observations and verified non-secret recovery manifests |
| `browser-results-*` | Assigned Playwright identities, durations, outcomes, wrapper timings and owned application evidence |
| `timing-history-backend`, `timing-history-api`, `timing-history-browser` | Successfully audited reusable costs with execution compatibility and source identity |

The backend audit verifies the original inventory, selection policy, plan identity, exact-once membership and successful phase outcomes. A collection manifest alone is never sufficient. Failed runs retain available evidence but cannot qualify an image. The Go JSON pipeline uses Bash `pipefail`; writing a report cannot turn failed tests into a successful candidate build.

Coverage instrumentation remains enabled in every backend shard. Only raw data is produced there; the audit job combines it and generates XML/HTML once. GitHub artifact uploads explicitly include hidden coverage files. Tool downloads use Dockerfile pins, bounded transport retries and SHA-256 verification; business assertions are not retried into success.

Committed backend log intervals and embedded API costs are cold-start scheduling estimates. Precise phase reports distinguish execution from queueing and automatically inform later compatible plans. Skipped, failed-to-start, cancelled or incomplete execution cannot contribute zero or reduced successful costs. Browser wrapper initialization and cleanup are measured separately so repeated fixture costs are not omitted from shard estimates.

## Validation

Follow the repository's [delivery and test requirements](../AGENTS.md#交付与测试要求). Local execution is limited to tests for changed behavior and affected call paths, selected by explicit files, node IDs, packages or case filters. Never run the full project or a component's full test suite locally, including through accumulated directory, shard or subagent runs. Required lint, type checks and build checks remain in place. Documentation-only changes need no local tests.

Use the existing `Qualify and Publish Application` workflow's manual dispatch on the implementation branch with `publish=false`. It executes candidate, static, backend, integrated API and browser gates without changing registry tags. API qualification requires all current Huawei cases and verified cloud cleanup. Confirm the source SHA, complete successful gates, all three exact-once audits and owned cleanup before comparing elapsed times. For E2E engine changes, also run the API workflow with reuse disabled to check isolation.

Bind the dispatched run ID to the latest pushed commit, then have the primary agent start a single persistent wait command:

```bash
gh run watch <run-id> --exit-status --interval 60 --compact > <log-path> 2>&1
```

Wait silently for this command to exit. Do not read its log or progress, send progress updates or continue other work during the wait. Neither the primary agent nor any subagent may repeatedly poll the same run or job through `gh run view`, `gh run list`, `gh api` or other GitHub interfaces. If the execution tool yields before completion, continue waiting for the same process. The CLI refreshes internally every 60 seconds; a user message may interrupt the wait, and a command interruption or connection failure is not a workflow conclusion. After the command finishes, read its log and inspect the final result once:

```bash
gh run view <run-id> --json headSha,status,conclusion,jobs,url
```

Require the exact latest commit and successful candidate, static, all backend shards and their audit, all API shards covering the required ordinary/Huawei cases and their audit, all browser shards and their audit, and final qualification. On failure, inspect failed steps with `gh run view <run-id> --log-failed`, fix the cause, run only related local checks, commit and push, then repeat full qualification for the new commit. Old successful runs or incomplete gates do not qualify it.

The reference qualification is [36148282102](https://github.com/xyqyear/mc-admin/actions/runs/36148282102), source `45a47640dedb60948b82418d5c1f989377e91af4`: 56:14 overall including publication, 55:18 from workflow creation through qualification, 55:01 backend gate, 2,183 passing backend cases, 81 API cases and six browser journeys. Test counts may grow with infrastructure regression coverage; the collected catalog, rather than those historical counts, determines completeness. Compare test steps and whole gates separately, and report changed runner availability or preparation costs alongside the results. The [measured balancing results](ci-balancing-results.md) record the complete successful implementation qualification and its remaining bottlenecks.

The unified-matrix qualification is [37337615626](https://github.com/xyqyear/mc-admin/actions/runs/37337615626), source `af7ebfd34fd3dd74cce38de80491aa6f8daca9a4`. Candidate, static, nine backend shards and their audit, five API shards and their audit, two browser shards and their audit, and final qualification all passed without publication. Audited evidence contains 2,417 backend nodes, 85 passing API cases with all 159 deployed operations observed, and eight browser cases. The API plan froze compatible history from run `37332724209`; its Huawei Minecraft case shared shard 3 with seven ordinary cases, and its reconciliation case shared shard 5 with thirteen ordinary cases. Provider dependencies selected protected authorization for those two mixed runners; all owned local/cloud cleanup passed. The same source also passed [credential-free regression with reuse disabled](https://github.com/xyqyear/mc-admin/actions/runs/37337623874): 83 cases in four ordinary shards with complete coverage and cleanup. Indivisible backend files retain explicit soft-target exceptions.

## Huawei cloud qualification

Huawei scenarios execute within the unified `e2e-tests.yml` matrix on trusted main/scheduled/manual qualification and release calls. Shard provider dependencies bind the protected `dns-e2e` Environment with `HUAWEICLOUD_AK` and `HUAWEICLOUD_SK`; deployment refs remain restricted to main, release tags and explicitly authorized qualification branches. A trusted mixed runner holds its required provider configuration while executing all assigned ordinary and Huawei groups. Ordinary PR regression selects no cloud dependencies and receives no cloud credentials. Complete API qualification independently requires every current Huawei case, successful results and exact cloud scope cleanup; missing credentials, cancelled/missing execution or residual records fail its aggregate gate.

Environment variables `HUAWEICLOUD_DNS_ZONE`, optional `HUAWEICLOUD_DNS_PARENT` and `HUAWEICLOUD_DNS_REGION` configure the dedicated namespace without committing account domains. Restrict the IAM identity to its test zone ID; each environment gets a separate descendant. EXIT and unconditional recovery stop owned writers and reclaim cloud records using validated non-secret manifests after success, failure or cancellation. Local Docker cleanup does not replace cloud verification. Explicit manual selection can disable reuse. See [DNS qualification and recovery](../e2e/suites/dns/README.md).
