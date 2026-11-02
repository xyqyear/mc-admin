## Context

沿用 Minecraft adapter、Runtime、monitoring、players 和 RCON API 的现有业务边界。玩家查询是后台校准，对外在线列表读取数据库；优化重点是减少 Compose 调用和给 RCON 增加容器内执行期限。

## Goals / Non-Goals

使用 Docker API 替换 Query/RCON 的 Compose exec，保持业务结果与失败边界。无需验证 GNU 版本、维护能力缓存、安装工具、管理远端 PID 或修改快照机制。

## Decisions

### 工具选择与参数

在一次 Engine exec 中运行固定 POSIX shell：command -v gnutimeout 成功则选它，否则选 timeout，随后 exec 所选工具。通过独立 argv 传递期限及业务命令；RCON 文本不拼接进 shell。工具缺失时失败，业务失败时不回退重发。

Query 使用保存的正有限秒数，RCON 执行期限为 8 秒；两者指定 --kill-after=1s。外层 RCON 预算为 10 秒。排队和准备消耗扣入剩余时间，给信号宽限和结果传输留出余量。Query 外层等待比保存的执行期限多留 3 秒。接受 timeout 实现的轮询延迟及标准进程组终止边界：不保证回收主动脱组或主命令退出后留下的后台后代。RCON 超时不能撤销已提交给 Minecraft 的命令。

### Docker 适配器

Runtime 拥有有限并发命令线程池，独立于 DockerReader。单次调用拥有 SDK 客户端和输出连接，有限 I/O 等待，结束即关闭。使用 SDK create/start/inspect，非交互、无 TTY；输出读取遵循 Docker 帧格式及绝对截止时间，不能依赖 SDK 默认的无限流读取。按真实退出状态确认成功，124/137 返回超时类错误，其他非零为命令失败；不输出原始 stderr 或命令。

沿用 DockerReader 核验项目目录、标签、服务及容器名，绑定 container ID 和 StartedAt。执行前核验该实例仍运行且健康；Query 降级复用同一个目标，不改投替代容器。路由只做 HTTP 映射，MCInstance 统一获取可执行目标，避免重复健康读取。

排队取消不提交命令，开始后的取消不声称远端立即停止。已启动 timeout 独立执行，SDK 工作具有有限期限。Runtime 关闭停止接受调用，排空已提交工作后关闭线程资源；不以取消 asyncio 等待冒充线程结束。不会自动重试 RCON。

## Validation

真实隔离容器覆盖工具优先级、普通 timeout 回退、缺失、参数保真、非零结果、普通管道及忽略 TERM 的超时、非 root、取消/关闭和实例改变。传输故障使用受控边界，验证不会无限等待或重发；慢命令期间监控独立可用。

业务与 API 覆盖 Query 空列表/降级/双失败保持在线状态、消息顺序、认证及 404/409/502/504、错误脱敏。执行定向快照保护回归及必要静态检查。隔离环境交替比较旧/新完整路径，Query/RCON 各 100 次，记录首调用、p50/p95、失败率和调用方 CPU；报告实测收益，不要求 Rust 轮询延迟消失。

## Risks / Trade-offs

原生 timeout 不能回收任意后代；外层断线无法证明游戏操作未发生，故不重发。工具选择接受已有实现，不安装或切换系统默认命令。

## Migration Plan

无需数据迁移；回滚应用镜像可恢复原调用路径。更新拥有行为的组件文档和规范，定向验证后提交推送并完成最新 SHA 的 qualification。发布部署独立进行。
