## Why

当前页面观察会重复启动 Compose 查询、为每个 CPU 请求等待一秒，并触发子进程结束后的全机进程扫描。2026-10-23 的线上调研已确认这些路径是主要负担；截至 `029c6fe5`，相关实现仍未改变。需要让观察成本主要取决于服务器数量和采样周期，同时保留操作准入、取消和恢复保障。

## What Changes

- 引入 Runtime 管理的共享监控读模型：容器状态、Java CPU、容器内存与 I/O、宿主机资源统一后台采样；目录占用采用独立低频队列。
- Docker 状态读取使用 Engine API；生命周期命令继续使用 Compose。操作前置校验直接读取当前状态，不依赖监控缓存。
- CPU 使用连续计数器差值，HTTP 返回最近样本及新鲜度；启动预热、采样失败、停止和实例替换具有明确语义。
- 前端由已登录布局中的唯一观察者刷新监控查询，总览、侧栏和详情通过同一 Query 缓存选择数据。维护状态从既有权威所有者读取，任务进度和终态继续使用现有事件流。
- 子进程确认增加“进程组已不存在”的快速路径；仍存在、无权限或不确定时保留现有身份校验、扫描、pidfd 清理及恢复阻塞。
- **BREAKING**：当前版本的分散监控 HTTP 接口合并为认证的 `/api/monitoring`；同步迁移所有前端、API E2E 和其他仓库内调用方，删除旧路由及重复查询实现，不保留兼容分支。
- 非目标：备份/prune 调度、地图渲染、数据库重构、多 worker、监控历史数据库、Docker 命令执行语义及任务事件协议重构。

## Capabilities

### New Capabilities

- `runtime-monitoring`：共享监控观察、指标口径、新鲜度、实例隔离、故障降级和前端会话生命周期。

### Modified Capabilities

无。`operation-recovery` 的写入停止确认和 `operation-refresh-sync` 的事件刷新要求继续原样成立；本次以回归测试验证这些不变量。

## Impact

- Backend：Minecraft Docker 读取适配器、系统资源读取、Runtime 生命周期、监控 API、服务器维护读模型、操作进程退出确认。
- Frontend：新增监控 feature，由应用层组合；迁移 servers/system 监控查询、总览、侧栏、详情及操作后的失效映射。
- API：替换服务器 status/maintenance/cpu_percent/memory/iostats/disk-usage、servers/overview 及 system info/cpu_percent/disk-usage 监控读取；服务器配置/列表、任务接口和 system health 保持各自职责。
- Persistence：不增加指标表，不改变操作日志及 ProcessIdentity 格式；历史未完成操作的恢复能力必须保留。
- Docker：复用已安装的 Docker Python SDK，增加有界直接读取；不新增容器权限、守护进程、部署服务或 Compose 生命周期替代实现。
- Verification/docs：配套定向后端、前端、真实 Linux 进程、Docker/API/browser 测试和隔离性能比较；实现时更新组件设计文档与 E2E 覆盖索引。
