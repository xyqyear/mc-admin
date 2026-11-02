## Why

玩家 Query 和 RCON 仍经 `docker compose exec` 调用，且部分镜像默认的 uutils timeout 0.8.0 每 100 ms 检查一次结束状态。线上原始镜像已自带 GNU timeout：保持查询逻辑，改走 Docker API 并选择该工具即可减少开销，无需自建进程管理框架。

## What Changes

- Query、RCON 和服内消息通过一个薄的 Docker 命令适配器执行；服务器创建、启停和重建继续使用 Compose。
- 每个运行实例首次使用时识别 GNU timeout：优先 `gnutimeout`，其次验证 GNU 版 `timeout`；缓存结果，容器替换或重启后重新识别。
- 超时及信号处理交给容器里的 GNU timeout，使用现有业务限时及固定 `--kill-after=1s` 兜底。Python 负责异步调用、连接限时、退出码和结果，不主动管理容器进程组。
- 保持 Query → RCON 降级、玩家在线状态、RCON 参数、消息顺序、权限及 HTTP 响应契约；日志提供安全的退出码与耗时。
- 明确采用 GNU timeout 的标准进程组边界，不承诺回收主动脱离进程组或主命令退出后留下的任意后台后代。

非目标：新增门控协议、pidfd、宿主机进程扫描、看门狗、任务持久化、用户配置项，或者修改游戏镜像、系统默认命令、快照/回档及 Compose 生命周期实现。保存的 Query 超时不自动调整。

## Capabilities

### New Capabilities

- `container-command-execution`：正确选择容器自带的 GNU 限时工具，通过直接容器执行提供查询和命令结果，保留现有失败与权限边界。

### Modified Capabilities

无。现有监控、快照和持久化操作规范继续适用。

## Impact

- **Backend**：Docker 命令适配器、Runtime 资源管理、`MCInstance` 及 RCON 路由；移除 Compose 的容器内 exec 入口，沿用现有 Docker SDK 与容器选择规则。
- **Frontend / API**：不新增页面、端点和字段；保留成功输出及 404/409/502/504 分类。
- **Persistence / configuration**：不新增迁移或配置；Query 模板、限时和玩家同步周期保留，RCON 沿用现有 10 秒预算。
- **Docker**：当前 java21/java25 原始镜像有 GNU 9.7 的 `gnutimeout`；java17 原始镜像的 `timeout` 是 GNU 8.30。无需安装包或额外权限；未来镜像缺少依赖时明确报告，不自动安装或静默使用 Rust 实现。
- **Validation / docs**：覆盖两种命令名、冷/热缓存、真实超时、降级、RCON/消息、取消与关闭；更新相关后端文档和 API E2E 覆盖。性能报告比较完整调用路径。
- **Breaking changes**：没有端点、数据库或保存配置的破坏性变更；受支持镜像需要提供 GNU timeout。采用其标准终止语义，不把它扩大为任意后台进程回收保证。
