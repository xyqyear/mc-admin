# 第一轮实现与验证

验证日期：2026-09-27。验证针对本轮实现，未执行版本发布。业务范围见 [非快照操作清单](../../../backend/docs/non-snapshot-operations.md)；[快照与恢复下一轮需求](../../../docs/snapshot-recovery-roadmap.md)保持为后续设计。

## 实现边界

服务器启停、重启、下线、创建、删除、登记同步，文件/存档删除，地图初始化，手动自检/DNS，以及上传 SHA256 和最终发布，使用现有 durable task/journal。各功能拥有 worker、会话和清理责任；地图初始化与登记同步从路由拆入功能模块。原来已经后台执行的任务不重复包装。

前端保留提交、等待、进度和关闭限制，确认任务终态后才执行成功/失败处理。查询失败保持忙碌并提示重连。总览、详情、控制台显示维护原因和任务入口；地图、自检、DNS、创建和登记同步可以发现当前任务。Docker 命令完成与 Minecraft 就绪分开表示。快照、恢复、回滚、预览及仓库维护的执行逻辑未迁移。

接口契约包含 155 个 HTTP 操作、3 个 WebSocket 路由及 23 组代表性路径。已核对旧自检执行流、旧哈希执行流的移除和新的任务受理响应；现有路由的鉴权、CSRF 及公共事件/任务进度协议没有意外变化。契约测试直接比较当前审阅过的 fixture，不再在测试中逐项补丁旧 fixture。

## 验证结果

| 范围 | 结果和证据 |
| --- | --- |
| 后端任务、服务器、文件、存档、自检、DNS、地图、operation、world、snapshot、架构 | 范围运行 1,220 项：首次 1,219 通过，1 项仍期待文件删除返回 200；调用迁移后该快照端点测试类 17 项全通过。另有 1 项被原有选择规则排除。日志 `/tmp/mc-admin-tasks-regression.log`、`/tmp/mc-admin-task-snapshot-endpoints-final.log` |
| 最新任务身份/上传清理/任务鉴权/契约/旧版本数据库升级专项 | 37 项通过，包含并发受理、同名实例替换、删除不等待自己、创建关闭回滚、哈希取消和发布关联。日志 `/tmp/mc-admin-task-contracts-complete.log` |
| 后端静态检查 | `uv run ruff check .`、`uv run pyright` 通过 |
| 前端 | typecheck、lint、导入边界、架构测试及 155 项 Vitest 通过；生产镜像构建通过。日志 `/tmp/mc-admin-task-frontend-complete.log`、`/tmp/mc-admin-task-build-complete.log` |
| Go 框架 | gofmt、vet、race 测试通过，日志 `/tmp/mc-admin-task-go-final.log` |
| 真实部署 API | `e2e-e504908ca1da`：29/29 通过，随机顺序、`--no-reuse`、2 workers/1 Minecraft slot。覆盖生命周期、删除排空、创建/登记、文件、上传、地图首次/缓存/force、自检和 DNS 故障边界 |
| 真实浏览器 | `browser-59fd7e4f61b5`：7/7 通过，含任务等待、编辑草稿、配置冲突、会话/控制台重连、恢复中断与回滚、过期清理预览；总览补充后 `browser-d06ae4abd1ca` 复测总览/地图观察和生命周期 2/2 通过 |
| 测量脚本迁移 | 本地及真实部署各 2 个样本完成上传、哈希、发布和精确字节核验；普通文件备份恢复也通过。报告 `/tmp/mc-admin-task-workload.json`、`/tmp/mc-admin-task-deployed-workload.json`。轮询请求数按样本记录，进度事件数量不作为业务一致性断言 |
| OpenSpec | `openspec validate background-non-snapshot-operations --strict` 通过 |

API 和完整浏览器运行使用镜像 `sha256:40a3e05beaca6a8aad74f189b9861e373ed64c800da811278a7e8c0cc4a29eaa`；总览补充后的最终镜像为 `sha256:d4431e1f60e0bc44b755cc6016614983ee668e2193d0c3c236846bff9e59c015`，后端生产代码相同。最终镜像也运行了两条浏览器复测和真实 HTTP 测量。

## 环境与首次失败记录

- 初次 API 回归中的生命周期历史来源、创建返回值及删除维护类型仍按旧契约断言。已迁移调用/断言并独立复测，最终 29 项完整运行全通过，没有放宽业务结果校验。
- 官方 Minecraft/地图客户端下载发生过超时。浏览器使用仓库既有的真实 1.21.11 本地 JAR 镜像和经过官方来源/SHA1 校验的客户端输入；真实渲染、Restic 和业务 API 保持不变。最终 API 地图用例仍由真实 mcmap 下载客户端，并通过首次初始化、缓存复用和 force 检查。原失败运行 `e2e-f9199fee9193` 保留。
- 主机 pnpm 提示 Node 26 与项目 Node 24 要求不符；生产镜像内使用 Node 24 完成前端类型检查和构建。主机测试通过不替代生产构建证据。
- 公有 DNS 账户未使用；`dns.owned-edge-reconciliation` 在隔离环境中运行真实 SDK 和 MC Router 故障场景。外部账户用例不计为已验证。
- 唯一保留旧哈希流调用的脚本是 `e2e/scripts/deployment_rehearsal.py`，用于向旧发布镜像准备升级前数据；当前应用不提供该接口。

测试均使用 runner 拥有的临时环境并完成清理。没有操作用户开发服务器、现有 Minecraft 实例或已有数据库锁文件。
