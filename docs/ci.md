# CI scheduling and timing evidence

The release qualification graph builds one immutable candidate while static checks and backend tests run independently. API, browser and Huawei DNS checks consume the same candidate; qualification requires every gate to succeed. See [release qualification](release.md) for source and image identity checks.

## Scheduling budget

Backend tests use four independent GitHub-hosted runners. Each runner executes pytest sequentially; no pytest worker processes share Docker fixtures. The planner discovers the complete current inventory, retains file/shared-fixture grouping, and assigns the longest estimated groups first. Capability requirements are the union of the actual selected tests. New files use a positive fallback cost and enter the inventory without workflow edits. Committed timing history affects scheduling, never coverage or eligibility.

API tests use three runners, each with two workers and one Minecraft slot. Fresh cases and reusable recipe groups remain indivisible during shard assignment. The planner balances estimated execution and Minecraft occupancy; the scheduler dispatches groups whose resource requirements currently fit. Seeded order still changes execution order within that assignment. Environment ownership and capacity reservation continue through teardown. See [API execution contracts](../e2e/docs/architecture.md).

The normal overlap after candidate construction is four backend runners, three API runners, one browser runner and one serial Huawei DNS runner. Account-wide capacity and other repository runs can still introduce waiting. Job creation-to-start time includes workflow dependencies and matrix constraints; it is not a direct measure of exhausted account quota.

Standalone push/PR runs use separate backend, API and static concurrency groups and cancel superseded executions. Manual API runs and reusable qualification children use their run ID, so a later branch push cannot cancel them or their caller. Release promotion retains its existing serialized, non-cancelling policy. Candidates or qualification receipts are not reused across unrelated runs.

## Evidence

| Artifact | Evidence |
| --- | --- |
| `backend-test-inventory` | Full inventory and deterministic shard plan |
| `backend-test-shard-N` | Selection manifest, precise setup/call/teardown timings, JUnit and raw coverage |
| `backend-test-reports` | Audited shard evidence and centrally combined coverage reports |
| `frontend-test-results` | Vitest JSON with individual test outcomes and durations |
| `go-test-results` | Race-enabled Go test JSON events, including per-test and package elapsed times |
| `e2e-results-N` | API plan, lifecycle timings, outcomes and explicit redacted diagnostics |
| `huawei-dns-results` | Cloud case/coverage results, actual DNS and Minecraft observations, candidate identity and verified cleanup manifests |
| `browser-results` | Playwright case durations, outcomes and owned application evidence |

The backend audit verifies the original inventory, selection policy, plan identity, exact-once membership and successful phase outcomes. A collection manifest alone is never sufficient. Failed runs retain available evidence but cannot qualify an image. The Go JSON pipeline uses Bash `pipefail`; writing a report cannot turn failed tests into a successful candidate build.

Coverage instrumentation remains enabled in every backend shard. Only raw data is produced there; the audit job combines it and generates XML/HTML once. GitHub artifact uploads explicitly include hidden coverage files. Tool downloads use Dockerfile pins, bounded transport retries and SHA-256 verification; business assertions are not retried into success.

Historical backend log intervals and API costs that subtract estimated resource waiting are initial scheduling estimates. Precise phase reports from current runs distinguish actual execution from queueing. Update reviewed cost data from comparable successful runs; do not reduce weights by counting skipped or failed-to-start tests as fast cases.

## Validation

Follow the repository's [delivery and test requirements](../AGENTS.md#交付与测试要求). Local execution is limited to tests for changed behavior and affected call paths, selected by explicit files, node IDs, packages or case filters. Never run the full project or a component's full test suite locally, including through accumulated directory, shard or subagent runs. Required lint, type checks and build checks remain in place. Documentation-only changes need no local tests.

Use the existing `Qualify and Publish Application` workflow's manual dispatch on the implementation branch with `publish=false`. It executes candidate, static, backend, API, browser and Huawei DNS gates without changing registry tags. Confirm the source SHA, complete successful gates, backend exact-once audit, API union audit and owned cleanup before comparing elapsed times. For E2E engine changes, also run the API workflow with reuse disabled to check isolation.

Bind the dispatched run ID to the latest pushed commit, then have the primary agent start a single persistent wait command:

```bash
gh run watch <run-id> --exit-status --interval 60 --compact
```

Use only this existing command's output for progress updates. Neither the primary agent nor any subagent may repeatedly poll the same run or job through `gh run view`, `gh run list`, `gh api` or other GitHub interfaces while waiting. The CLI refreshes internally every 60 seconds; a command interruption or connection failure is not a workflow conclusion. After the command finishes, inspect the final result once:

```bash
gh run view <run-id> --json headSha,status,conclusion,jobs,url
```

Require the exact latest commit and successful candidate, static, all backend shards and their audit, all API shards and their audit, browser, Huawei DNS and final qualification. On failure, inspect the failed steps with `gh run view <run-id> --log-failed`, fix the cause, run only related local checks, commit and push, then repeat full qualification for the new commit. Old successful runs or incomplete gates do not qualify it.

The reference qualification is [36148282102](https://github.com/xyqyear/mc-admin/actions/runs/36148282102), source `45a47640dedb60948b82418d5c1f989377e91af4`: 56:14 overall including publication, 55:18 from workflow creation through qualification, 55:01 backend gate, 2,183 passing backend cases, 81 API cases and six browser journeys. Test counts may grow with infrastructure regression coverage; the collected catalog, rather than those historical counts, determines completeness. Compare test steps and whole gates separately, and report changed runner availability or preparation costs alongside the results. The [measured balancing results](ci-balancing-results.md) record the complete successful implementation qualification and its remaining bottlenecks.

## Huawei cloud qualification

`dns-tests.yml` runs on main-branch changes, daily at 19:23 UTC, manual dispatch and reusable release qualification. It has one worker and one Minecraft slot. The `dns-e2e` Environment holds `HUAWEICLOUD_AK` and `HUAWEICLOUD_SK`; restrict deployment refs to main, release tags and explicitly authorized qualification branches. Pull requests and ordinary regression jobs receive no Huawei credentials. Missing credentials, cloud failure or residual owned records fail qualification. Environment variables `HUAWEICLOUD_DNS_ZONE`, optional `HUAWEICLOUD_DNS_PARENT` and `HUAWEICLOUD_DNS_REGION` configure the test namespace without committing account domains. Use a dedicated test zone and restrict the IAM identity to its zone ID; each environment gets a separate descendant. Both the runner and an unconditional workflow step reclaim test records after success, failure or cancellation. Manual dispatch can disable reuse. See [DNS qualification and recovery](../e2e/suites/dns/README.md).
