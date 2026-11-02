## Why

玩家查询和 RCON 仍通过 `docker compose exec` 执行，容器里的 `uutils timeout` 又增加了约 100 ms 的正常返回等待。线上只读对照中，Query 经 Compose 的中位耗时为 186.5 ms，改走 Engine API、保留 timeout 后为 137 ms，而查询脚本本身仅需约 7–9 ms；应同时消除重复 CLI 启动和固定等待，并保留真实的超时清理。

## What Changes

- Query、RCON 和服内消息统一通过 Runtime 拥有的容器命令执行器调用 Docker Engine API；ComposeManager 只保留服务器生命周期操作。
- Python 异步等待实际完成并管理截止时间，移除正常执行路径上的外部 `timeout`。超时、取消和关闭必须处理真实容器进程，不能仅取消客户端等待。
- 复用现有容器归属、服务器代次和 Linux 进程身份机制；在执行命令前建立所有权，命令完成、取消或异常后的清理由同一个执行器负责。
- 保留容器侧有限的失联保护，防止 admin 被强制终止后遗留无限等待的查询。它不得引入固定轮询延迟、安装包、常驻代理或游戏存档文件。
- 合并同一次执行中的重复健康检查，保持执行时的权威校验、Query → RCON 降级、玩家会话语义、消息顺序与现有 HTTP 契约。
- 用安全的阶段、耗时和退出码记录诊断信息；预期 Query 降级不输出原始命令及完整异常值。

非目标：改写 Compose 启停/创建/重建、直接实现 Minecraft 网络协议、调整玩家同步周期或已保存的 Query 超时、重做监控/控制台、改变快照/回档流程、修复全局日志重复输出。本次提案不修改或部署线上系统。

## Capabilities

### New Capabilities

- `container-command-execution`：容器命令的完成、限时执行、取消与失联清理、实例隔离及现有玩家/RCON 结果的行为保证。

### Modified Capabilities

无。现有监控、操作恢复及快照规范继续适用，不改写它们的业务规则。

## Impact

- **Backend**：`app/minecraft/docker/`、`MCInstance`、Runtime 构造与关闭、RCON 路由和玩家同步调用路径；按需提取 `app/operations/processes.py` 中可复用的身份/清理原语，保留原有调用方。
- **Frontend / API**：没有新增页面、端点或响应字段；保留认证规则及 RCON 的 404/409/502/504、成功输出和消息逐行语义。错误文本使用安全的中文说明。
- **Persistence / configuration**：不引入数据库迁移、每次查询的持久化任务记录或配置开关；保留 `players.query.query_command`、`players.query.timeout` 和既有 RCON 限时。持久化操作上下文存在时继续遵守原 journal 所有权。
- **Docker**：复用部署已有的本地 Engine socket、宿主机 PID 可见性及 Linux pidfd 支持。可行性验证必须先确认权限和受支持镜像的最小门控脚本；不得以增加 privileged、挂载游戏文件或静默退回旧执行链路来绕过。
- **Validation / docs**：增加真实 Docker 与定向 API E2E 的结果、取消、并发和清理覆盖，保存可复核的前后性能数据；同步 Minecraft、Runtime、监控、玩家、集成 API 及 E2E 覆盖文档。
- **Breaking changes**：没有计划中的 API、数据库或保存配置破坏性变更。无法安全建立进程所有权的环境必须在业务命令开始前明确失败；支持范围变化须在接入调用方前重新评审。
