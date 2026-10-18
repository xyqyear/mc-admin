# Self-Check Dashboard

The protected root route (`/`) renders `src/features/health/SelfCheckScreen.tsx`. It is an
operational dashboard, not a landing page.

## Data Flow

Raw API calls live in `features/health/api.ts`; response and stream-event contracts live in `features/health/contracts.ts`.

Query hooks:

- `useSelfCheckStatus()` polls `/api/self-check/status` for the catalog,
  current health state, and recent retained run summaries.
- `useSelfCheckRun(runId)` loads retained findings for a selected run.
- `useSelfCheckCatalog()` and `useSelfCheckRuns()` are available for narrower
  consumers.
- `useSelfCheckHealth()` derives unresolved warning and critical counts from
  the current health state for global indicators.

手动全量检查提交 `/api/self-check/run`，然后直接从共享任务 SSE 的 `progress_details`（`kind="self_check"`）读取累计 findings、当前检查项和已完成/总检查数；单项重跑也等待对应任务。按钮在真实终态前保持忙碌；断流保留进度、提示重连且不回退为 HTTP 进度轮询，重新进入页面可接上活跃自检。健康检查告警与执行失败分别展示。完成后由全局 operation observer 刷新 `queryKeys.selfCheck.all`。

## Page Behavior

实时 findings 受事件体积预算限制，截断时页面提示累计结果数；终态摘要不清除已经显示的 findings。完整结果读取失败时，“重试读取结果”只重读同一任务，不再次执行自检。依赖结果的操作保持禁用，读取成功后展示完整 findings 并解除忙碌状态。

The dashboard shows:

- summary counts for the displayed run
- manual run button
- every finding from the current health state, live task, or selected history run
- per-card rerun controls
- retained run history

Healthy and unhealthy runs are retained for the configured retention window, and
retained details include every finding.

Single-card reruns update the displayed card immediately and invalidate
self-check queries. After refresh, `/api/self-check/status` derives the same
current state from the latest full run plus later single-check reruns, filtered
to checks that are currently enabled.

Selecting a retained run switches the result panel to that historical result.
The result header offers a return action that clears the selected history run
and displays the current health state again.

For `server.game_port_consistency`, server-associated mismatches and failed
properties reads/parses include a `定位 server.properties` link in the remediation
area. The shared current/history finding renderer derives it from `server_id`,
status, and `evidence.error_stage`; Compose/status failures do not offer this
file repair link. Evidence keys have Chinese display labels. Backend remediation
remains plain text, with no new action fields or Markdown parsing.

The route is `/server/<encoded-server-id>/files` with `path=/`,
`q=server.properties`, and `regex=false` built by `URLSearchParams`. The existing
file browser owns filtering, reload/back navigation, authentication, and editor
opening. The link does not open or change a file automatically. Remediation
explains saving and restarting, plus conditional Compose correction/recreation
when an explicit environment setting would override the file.

## Navigation

The sidebar labels `/` as `系统自检`. Submenus stay collapsed on the root route.
If the current health state has unresolved warning or critical findings, the
sidebar item shows a badge and the main layout shows a global alert strip.

## Cron UI Coupling

`self_check` is registered as a backend system cron job. Cron API types include
`is_system` and registration defaults. The cron management page:

- displays a `System` badge for system jobs
- hides pause/resume/cancel controls for system jobs
- keeps task type locked in edit mode
- allows editing name, cron expression, seconds field, and params
