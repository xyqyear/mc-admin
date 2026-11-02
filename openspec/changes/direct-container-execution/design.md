## Context

动机与范围见 [proposal](proposal.md)。设计沿用 [Minecraft adapter](../../../backend/docs/minecraft.md)、[Runtime](../../../backend/docs/runtime.md)、[monitoring](../../../backend/docs/monitoring.md)、[process ownership](../../../backend/docs/operations.md)、[recovery](../../../backend/docs/operation-recovery.md)、[players](../../../backend/docs/players.md) 和 [RCON API](../../../backend/docs/bot-integration-apis.md) 的边界。

现有部署及 API E2E 使用 `pid: host` / `--pid host`，后端已有 pidfd、启动时刻及进程归属验证。游戏容器已经依赖 Bash 执行 Query。Docker SDK 是现有依赖；状态、top 和网页控制台已经直接调用 Engine，剩余 Compose exec 入口只有 Query 和 RCON。

2026-11-02 对 fkm/xlg 的只读诊断提供以下基线；它不是新方案的性能承诺：

| 从 admin 容器内计时，中位数，每项 10 次 | 空命令 | Query，保留外部 timeout |
| --- | ---: | ---: |
| Compose exec | 82 ms | 186.5 ms |
| Docker CLI exec | 40.5 ms | 138.5 ms |
| Engine HTTP API，curl create/start/inspect | 38.5 ms | 137 ms |

Query 脚本的另六次分段测量为 7–9 ms；`timeout true` 约 105 ms。250/500/1000 ms 对照每台各 20 次，只有 xlg 的 250 ms 组出现一次 124 退出。增加限时与替换执行链路是不同问题，本次保留现有配置值，也不声称 API 能修复 UDP 丢包或无响应。

官方边界依据：[SDK exec](https://github.com/docker/docker-py/blob/main/docker/api/exec_api.py)、[流关闭](https://github.com/docker/docker-py/blob/main/docker/types/daemon.py)、[Engine exec inspect](https://docs.docker.com/reference/api/engine/)、[asyncio timeout](https://docs.python.org/3/library/asyncio-task.html#timeouts)。输出流关闭不等于进程被终止；exec inspect 只描述 exec 根进程，不能证明子进程全部退出。

## Goals / Non-Goals

**Goals:**

- 正常完成使用事件唤醒，不支付固定约 100 ms 的等待成本；执行链路不启动 Docker/Compose CLI 或外部 timeout。
- 将结果、身份、截止时间和必要清理放在一个执行所有者内，使 Query、RCON 不各自实现取消逻辑。
- 避免慢命令阻塞监控、事件循环和其他服务器；执行容量、缓冲与关闭有界。
- 命令的容器、进程及输出保持一一对应；故障不误杀 Java、其他命令或重建后的同名实例。

**Non-Goals:**

- 不建设通用远程作业平台、任务队列、容器代理或新的持久化执行表。
- 不把 RCON 已经交给 Java 的游戏命令解释为可撤销事务。客户端进程结束不能撤销游戏内副作用，也不能保证游戏命令未被接受。
- 不为省时取消实例验证、输出结束确认或故障清理；不把后台状态缓存用于授权执行。

## Decisions

### 1. 三个具体职责，复用现有依赖

| 所有者 | 职责 |
| --- | --- |
| `ComposeManager` | up/down/start/stop/restart 等 Compose 生命周期协调 |
| `DockerReader` | 容器选择、归属核验、状态和 Java PID 读取 |
| `DockerExecutor` | 已核验目标上的有限命令、输出、退出码、限时和清理 |

执行器由 Runtime 构造和关闭。它拥有自己的 SDK 控制连接、有限控制调用线程及活动执行集合；不占用 DockerReader 的单线程队列。create/start/inspect 等阻塞控制调用在线程中运行且有网络超时，命令输出通过 exec socket 异步读取，不能把整个 `exec_run()` 塞进线程后仅取消 coroutine。

初始限制为全局 4 个活动执行、最多 16 个等待者，常量可供测试注入，不新增用户配置。等待有截止时间；容量不足返回安全的现有执行失败响应，不启动无主工作。取消中的执行保留容量，直到确认停止；清理不依赖另一个执行槽。连接和待执行工作的数量均有界。

不创建策略注册器、通用插件接口或多套 CLI/API 后端。`DockerExecutor` 的内部结果仅包含退出码、分离的 stdout/stderr、耗时及安全失败类别。输出上限初始为每次合计 8 MiB，超限必须清理并明确失败，不能截断后报告成功。

### 2. 执行前只解析一次目标，绑定实际实例

调用捕获当前 `ServerRef`。获得执行容量后重新验证代次、项目目录、项目标签、服务 `mc`、配置的容器名、完整 container ID 和启动身份，然后在命令放行前确认一致。复用 DockerReader 的选择规则，不按 `mc-<name>` 猜测容器。

执行 token 在本次调用内复用，合并 RCON 路由和 `MCInstance` 的重复健康检查；它不是跨请求缓存。Query 降级为 RCON 是一次新执行，需要重新验证。容器在解析后删除、同 ID 重启或同名重建时失败，不自动对新实例重试。

命令保持 argv 形式。RCON 文本作为单个参数交给 `rcon-cli`；仅现有受配置控制的 Query 模板交给 Bash。exec 继承运行容器的 user、environment 和 workdir，不重新套用尚未部署的 Compose 修改。

### 3. Python 管理正常限时，容器门控保证可清理

执行顺序为 `resolve → create → attach/gate → own → release → drain → inspect → settle`。只有归属已建立才允许业务命令启动：

1. 用 Engine 创建无 TTY、带受控 stdin 的 exec，运行固定、随应用版本管理的最小 Bash 门控脚本。它通过 `setsid` 建立独立进程组，先等待放行；业务命令不能读取控制 stdin。
2. 读取门控首帧，取得容器内身份；通过 exec inspect 的 host PID 建立对应关系。如果 `setsid` fork，只允许解析这个仍被门控阻塞的直接子进程，核对 PID namespace、启动时刻、容器归属和组长身份，不扫描整个宿主机寻找相似命令。控制帧与业务输出分别解析，异常或伪造的握手不能放行。
3. 获取真实命令组长的 pidfd，记录 `ProcessIdentity` 与 container incarnation，并在持有 pidfd 后重新校验。权限、PID 可见性、组隔离或能力检查失败时，关闭未放行门控，不运行命令。已有持久化 operation context 时按原 journal 规则登记；普通玩家读取不创建数据库任务记录。
4. Python 发送一次放行，异步消费 stdout/stderr，使用单调截止时间。结束后检查退出码和进程清理结果；EOF 或 HTTP 200 本身不是执行成功。
5. 超时、请求取消和 Runtime 关闭复用进程身份/pidfd 原语收尾：确认本次进程树及组归属，TERM、有限宽限、必要时 KILL，并确认退出、关闭 socket/pidfd 后释放容量。所有信号只能作用于这次 exec，禁止 container kill/stop、按名称重查 PID 或无身份校验的 killpg。

现有 `processes.py` 绑定 `asyncio.subprocess.Process` 的封装不直接套给远端 exec。只提取所需的身份捕获、拥有的句柄、停止与确认能力；本地子进程继续使用原封装和 journal 规则。正常结果优先走退出通知和已确认空组的快路径，不为每次查询枚举整棵 `/proc`；取消路径的额外枚举不影响正常延迟。

门控还有一个独立于 Python 存活的失联保护：固定 Bash 脚本利用阻塞的内建 `read -t` 等待控制连接关闭或硬截止，命令正常结束时立即回收等待者，不周期 sleep。等待者与本次命令处于已核验的独立组；失联后只终止自己的组，并有 TERM→KILL 的有限升级。硬截止覆盖命令预算加清理余量，不能无限等待 admin 重启。这样不需要游戏容器内 Python、外部 timeout、常驻进程、临时存档文件或新镜像挂载。

这部分必须先在隔离 Docker 环境做可行性验收，包括 Bash/setsid 行为、user/rootless 权限、setsid fork、stdin EOF、忽略 TERM 和强杀 admin。门控与失联等待者不能遗留进程；没有证明这点之前，不接入真实调用方。若既有支持环境需要新权限或安装程序才能成立，应修订设计，不增加不透明回退路径。

仅 `wait_for(to_thread(exec_run))`、关闭 socket、杀 Docker CLI 都不满足这个设计。直接重写 Query/RCON 网络协议虽能消除 exec，涉及网络可达性与凭据处理，本次不采用。

### 4. 明确三种时间预算

| 预算 | 规则 |
| --- | --- |
| 排队/目标解析/门控建立 | 每个阶段有界；Query 准备阶段最多 5 秒，RCON 共享现有总预算 |
| 业务执行 | Query 在放行时使用当前保存的 `players.query.timeout`，不擅自把 0.25 改为 0.5；RCON 保留请求内 10 秒执行限时并扣除排队/准备时间 |
| 清理 | 独立有限预算，初始 2 秒 TERM 宽限和 2 秒 KILL/确认预算；不得因业务时间耗尽而跳过 |

容器硬截止使用放行时的剩余命令预算加清理余量，门控放行前同样有有限等待。对外超时响应可能晚于业务截止，以完成必要清理；响应不得声称 RCON 游戏副作用已撤销。动态配置在每次执行时读取；超时值必须是有限正数，持久化的不可用值明确失败，不能退化为无限等待。

不自动重试业务命令。特别是 start 的响应丢失时，命令可能已经执行，必须按 exec ID 收尾而非重新发送 RCON。

### 5. 调用方保留业务语义

- Query 成功后返回相同玩家列表，包括真实空列表。禁用、配置缺失、非零退出或超时按既有规则降级；已启动 Query 必须完成清理后才降级。请求取消、应用关闭、实例更换及清理不确定不能触发第二次命令。
- RCON 保留 stdout/ANSI 处理和返回格式。认证拒绝不创建 exec；不存在、不健康、执行失败和超时分别保留 404/409/502/504。异常输出不可直接拼入公开错误。
- 服内消息仍按非空行串行发送，不并行或合并；一行失败后不重发已发送行。
- 玩家同步保持原周期及结果写入规则。Query 和 RCON 都失败时是未知观测，不批量标记玩家离线。
- 日志只记录服务器、命令类别、阶段、耗时、退出码及是否完成清理；不记录 argv、Query 模板、凭据、原始异常值。成功降级用一条简短 DEBUG 记录，全局 logger 重复输出另案处理。

### 6. Runtime 关闭和不确定清理

关闭先停止玩家生产者并拒绝新执行，再取消/排空等待者和活动执行，最后关闭控制连接、线程及日志/数据库依赖。重复取消不能打断已开始的清理。一个执行器关闭失败不跳过其他 Runtime 清理。

不能确认停止时，不宣称成功、已取消或允许同一目标无限增加新命令。执行器保留该 incarnation 的清理记录和容量限制，报告安全失败；只有明确停止或确认旧容器已结束才释放。关联现有持久化操作的执行仍遵循原 journal/recovery 阻塞，不能由本适配器清除。无关服务器及监控保持可用。容器失联保护负责 admin 被 SIGKILL 时的最终停止，不把每分钟的读取变成持久化任务。

## Risks / Trade-offs

- **Engine 没有可直接替代完整进程树清理的 exec 取消语义** → 门控前建立真实进程所有权，复用 pidfd；把隔离容器可行性验证放在第一步。
- **宿主机 PID 可见不等于具有信号或 `/proc` 读取权限** → 在实际受支持 user/镜像/部署中验证；不新增 privileged 或扩大权限以掩盖问题。
- **远端启动返回不确定、容器重启、PID 复用** → 绑定 generation/container/start identity、受控门控和 pidfd；禁止自动重发 RCON。
- **失联保护增加少量 shell 工作** → 使用阻塞等待和完成通知，成功后立即清理；不允许固定轮询或每次部署 helper 文件。性能验收包含这部分，不能只比较裸 exec。
- **RCON 断线后 Java 可能继续执行已经接受的命令** → 不声称回滚，保留错误语义，不重试；清理范围仅是本次客户端进程。
- **精确截止比 uutils 的检查周期更严格** → 保留配置值并单独统计超时率；若 250 ms 的真实失败率不可接受，另行根据实测决定阈值，不在重构中暗改。
- **身份原语调整可能影响快照子进程** → 仅提取共享机制，原接口继续使用；必须回归真实 Restic/回档取消、迟发子进程及 journal 清理不变量。

## Validation and performance acceptance

1. **协议与结果**：真实容器内的成功/失败、stdout/stderr 分帧与截断、空结果、大输出、中文及特殊参数、退出码、非 TTY；进程成功后的副作用用独立文件/状态断言验证，不能只断言 SDK 调用次数。
2. **生存期**：放行前、启动响应未知、输出等待、截止同时完成、用户取消、Runtime 关闭、SDK 失败及 admin SIGKILL；包含阻塞读取、子孙进程、忽略 TERM、重复取消、PID 复用和同名重建，确认无遗留且 Java/旁路哨兵不受信号影响。
3. **业务/API**：Query 成功与失败后 RCON、双失败不篡改在线状态、RCON 一次执行、服内消息行序和失败边界、未授权零副作用、现有 HTTP 响应；部署 API E2E 增补对应场景和覆盖清单。
4. **隔离性**：慢命令、容量耗尽与大输出期间，独立监控继续刷新、健康接口可读、取消可进行；状态判断不受旧监控样本授权。
5. **已有关键路径**：定向执行实际进程清理、Restic/世界恢复取消与生命周期相关测试，确认无快照或停服保护回归。Pyright、Ruff 及受影响 Go 包检查按组件规则执行。
6. **性能**：同一隔离机器/镜像/负载，交替运行旧路径、裸 API 参考和完整新执行器；包含配置/身份检查、门控、限时、收尾，记录冷/热路径、p50/p95、错误率及 CPU。Query/RCON 各至少 100 次正常观测，故障注入另列，不能剔除慢样本后宣称收益。

发布前目标：健康 Query 的完整新路径 p50 至少比旧路径减少 50%，p95 不回退；正常结束无固定约 100 ms 的等待台阶，新增 CLI/timeout 调用为零，故障/清理断言全部满足。几十毫秒是待测预期，不是已实现结果；未达目标先解释并调整设计，不删除保护以达标。生产仅可在后续明确授权下做少量只读验证，故障和负载测试都在隔离环境。

## Migration Plan

先完成门控/身份/失联清理的隔离验收，再实现执行器，最后统一接入 Query/RCON 并删除 ComposeManager.exec。没有并存的旧执行后端、数据库迁移或用户开关。正式接入时同步更新 backend 的 Minecraft、Runtime、monitoring、players、bot-integration-apis 文档以及 E2E 覆盖入口；进程所有权原语的变化更新 operations/recovery 的唯一说明。只有指令或阅读路由改变才修改 AGENTS.md；当前仓库未发现 CLAUDE.md，不新增重复文档。

本地只跑明确节点/文件/用例限定的相关测试。提交推送后使用最新 SHA 的 push qualification，不重复手动触发，核对完整执行或合法内容复用凭据。实现、发布与部署是后续独立步骤，本提案不自动发布。回滚前先正常排空容器命令；旧镜像继续读取相同数据库、配置和游戏文件。
