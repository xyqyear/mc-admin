## Context

`backend/docs/cron.md` 描述期望状态、注册状态及触发指纹；`backend/docs/operations.md` 和 `backend/docs/database-migrations.md` 描述资源持有、实例复核和迁移事务。当前 cron 永久绑定具体实例并根据历史时间推断归属，与用户要求按服务器名配置重启计划不一致。

## Decisions

### Logical target and single-execution identity

`ServerRestartParams.server_id` 是目标服务器的完整逻辑名称。显示名称只用于展示。每次触发调用公共服务器命令，在当次执行开始时解析当前服务器；取得资源后继续使用公共命令捕获的 `ServerRef` 复核，防止等待中的执行误作用于替换实例。缺失或停止的目标不调用 Docker 并记录跳过。计划暂停、取消或修改后，旧触发仍通过配置指纹和期望状态检查拒绝执行。

### Managed selection

保留 `managed_purpose="restart"`，区分服务器页面管理的计划与独立 cron 任务。按任务类型、用途和 `params.server_id` 精确匹配；优先取最小行 ID 的未取消计划，全部取消时取最大行 ID 的取消计划。选择不修改其他计划，也不删除或恢复它们。配置锁内检查和创建，避免取消数据库代次唯一索引后出现并发重复创建。

允许修改显示名称和目标参数；受管重启计划仍必须保持重启任务类型。删除服务器继续按目标参数精确取消活动重启任务，不取消相似名称服务器的计划。

### Migration and rollback

新增 `2026100700`，在 `2026100600` 后删除旧绑定索引、检查约束、`managed_server_generation` 和 `managed_binding_issue`。保留 `managed_purpose` 和所有其他字段、ID、参数、状态及历史；已发布迁移不改写。SQLite batch DDL 前建立真实事务，故障可回滚重试。

存在受管计划时拒绝降级到永久实例绑定，避免猜测历史代次或使有效计划重新不可注册。无受管计划时允许恢复空的旧列及约束。线上数据库通过先前获得的只读备份在本地独立副本演练，禁止触及原始备份或线上数据。

### API and UI

cron 响应移除两个绑定字段以及绑定专用 `blocked` 注册状态。通用配置错误继续用 `registration_error` 和 `failed` 展示并保留坏配置供用户修正。前端保留用途展示、目标参数与注册错误，删除实例永久绑定说明。

## Validation and documentation

调整按实例绑定的业务测试为逻辑目标测试；保留单次实例竞态保护测试。覆盖共同前缀、任意显示名称、同名实例替换、历史多计划、独立任务、暂停取消、并发创建、缺失或停止跳过、迁移保留和失败重试。真实 API E2E 覆盖对应公开行为；本地只运行定向测试和组件静态检查，最终完整验证由最新提交的非发布资格 CI 执行。

同步 `backend/docs/cron.md`、迁移文档、前端 cron 文档、根和组件 `AGENTS.md`、E2E 覆盖文档以及 `openspec/specs/operation-consistency/spec.md`。
