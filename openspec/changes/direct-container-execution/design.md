## Context

沿用 [Minecraft adapter](../../../backend/docs/minecraft.md)、[Runtime](../../../backend/docs/runtime.md)、[monitoring](../../../backend/docs/monitoring.md)、[players](../../../backend/docs/players.md) 和 [RCON API](../../../backend/docs/bot-integration-apis.md) 的业务边界。目标是优化两处容器内命令调用，不建设通用进程管理框架。

2026-11-02 按线上运行容器的实际镜像 ID，使用无网络、只读、无游戏目录挂载的一次性容器验证：

| 原始镜像 | 当前使用它的服务器 | 默认 timeout | 可直接使用的 GNU 工具 |
| --- | --- | --- | --- |
| java25，`45dfb63dcd91` | creative、vanilla、gtnh | uutils 0.8.0 | `/usr/bin/gnutimeout`，GNU 9.7 |
| java21，`5655907b668d` | fkm、xlg | uutils 0.8.0 | `/usr/bin/gnutimeout`，GNU 9.7 |
| java17，`537610f18403` | htxzq | GNU 8.30 | `/usr/bin/timeout` |

这些是镜像自带工具，不依赖容器运行后的人工安装。标签未来可变，能力识别以实际运行实例为准。

fkm/xlg 各五次交替测量全部成功：容器内 `timeout true` 为 104–105 ms，`gnutimeout true` 为 3 ms；原 Query 脚本经两者分别为 104–105 ms 和 8–9 ms。该数据不含 Docker 调用开销。另一组 admin 容器内测量，Compose/Engine API 执行同一 Query 的中位数分别为 186.5/137 ms，后者仍使用 Rust timeout。

依据：[uutils 0.8.0 的 100 ms 轮询](https://github.com/uutils/coreutils/blob/0.8.0/src/uucore/src/lib/features/process.rs#L125-L153)、[GNU timeout 语义](https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html)、[Ubuntu 软件包](https://packages.ubuntu.com/resolute/gnu-coreutils)。

## Goals / Non-Goals

**Goals:** 减少 Compose CLI 启动及 Rust timeout 的轮询延迟，保持现有查询结果、降级、RCON/消息及管理权限；使用镜像已有工具，不增加部署权限。

**Non-Goals:** 自建门控/看门狗/进程组协议、扫描宿主机进程、扩展 pidfd、回收任意逃逸后台进程、引入持久化任务或修改快照/回档、重写 Minecraft 网络协议、调整保存的查询超时。

## Decisions

### 1. 一层薄适配器，两个调用入口

| 模块 | 职责 |
| --- | --- |
| `ComposeManager` | 保留 up/down/start/stop/restart 等生命周期命令 |
| 现有 `DockerReader` | 按项目目录、标签和服务核验目标容器，提供实时状态 |
| `docker/commands.py` | GNU 工具选择、直接 Engine exec、输出与退出码 |
| `MCInstance` | Query/RCON 参数与结果解析，玩家降级逻辑 |

Runtime 拥有命令适配器及连接资源。采用现有 Docker SDK，不使用 Docker/Compose CLI 执行容器内命令。SDK 阻塞工作在独立、有限并发的执行资源中运行，与 DockerReader 的监控队列隔离；不在 FastAPI 主线程同步等待，不引入任务队列产品或额外配置。

使用 SDK 的 exec create/start/inspect 和输出处理能力，非交互执行关闭 TTY，保留 stdout、stderr 和退出码。连接与输出读取需要有效的 I/O 截止时间；不能假设 SDK 的 client timeout 自动限制整个 exec 流，也不能把取消 `to_thread` 当成线程已退出。这里仅管理本应用的连接/工作线程，不管理远端 PID。

### 2. 首次识别，热路径直接使用

复用实时容器选择规则，绑定完整 container ID 和 StartedAt。首次使用时依次检查：

1. `gnutimeout --version` 成功且确认 GNU 实现，选中它。
2. 否则检查 `timeout --version`，确认是 GNU 实现后选中它。
3. 都不满足则返回清晰的依赖缺失错误，不安装软件，不静默使用 Rust timeout。

缓存选中的命令及版本，按实际容器 ID + StartedAt 隔离。同一实例并发首次调用共享一次识别；重启、替换、删除或发现工具消失时使缓存失效，失败不永久缓存。每个受管目标只保留当前实例的条目；不缓存健康状态用于执行授权。

识别发生在首次实际使用，不阻塞应用启动。热路径不重复运行 `--version`，不在每次调用中执行选择工具的 shell 脚本。业务执行失败后不为探测或切换命令名自动重发 RCON。

### 3. GNU timeout 管理容器内限时

通过 Engine exec 传入 argv，核心调用为：

```text
Query: [gnu_timeout, --kill-after=1s, 保存的查询秒数, bash, -c, 原查询脚本]
RCON:  [gnu_timeout, --kill-after=1s, 本次剩余执行秒数, rcon-cli, 原命令]
```

Query 保留现有模板和 `players.query.timeout`，当前 0.25 秒不会自动改为 0.5 秒。RCON 沿用 10 秒预算，排队和准备消耗应扣除；服内消息仍按非空行逐行调用。`-k 1s` 是固定终止宽限，不是正常返回等待，成功时立即返回。

动态配置在使用时读取；零、负数或非有限超时不允许变成无限执行。命令继承运行容器的 user/environment/workdir，不应用尚未部署的 Compose 修改。RCON 文本是一个 argv 元素；只有原 Query 模板使用 Bash。

正常结果以 exec 真实终态与退出码为准。0 为成功，124 表示 timeout 到期，137 按终止失败/超时处理；137 本身不能唯一证明是 timeout 强杀，不编造原因。其他退出码按命令失败处理。Query 按既有语义降级，RCON 保留 502/504 错误分类，诊断不回传原始 stderr 或敏感命令。

### 4. 采用标准工具的边界

GNU timeout 默认向命令及其进程组发 TERM；指定 `-k` 后，如果被监控的主命令仍未退出，再发 KILL。普通 Bash Query 管道继承该组，沿用这个范围，不使用 `--foreground`。

它不承诺任意后代回收：主动建立其他进程组的后代可能不被覆盖；主命令已退出时，不继续扫描后台后代，`-k` 也不保证补杀这些后代。本方案明确接受该标准行为，不新增后台进程扫描或监督脚本。

排队期间取消不启动命令。命令开始后取消 Python 等待，不等于容器命令立即终止；已经启动的 GNU timeout 继续按自己的期限运行。正常关闭停止接受新调用并排空已有本地工作，再关闭 SDK 资源；网络故障按有限 I/O 等待返回结果未知，不假装已经杀死远端进程。应用崩溃后依赖已经启动的 GNU timeout，不增加自建失联机制。

RCON 可能已把命令交给 Java；终止客户端不能撤销游戏副作用。不自动重试 RCON，不用 container stop/kill 处理查询超时，不改动现有持久化操作和恢复框架。

### 5. 保持调用方语义

Query 成功空列表仍是有效观测；Query 与 RCON 都失败时不批量标记玩家离线。因请求取消或实例改变而中止时不对新实例启动降级。RCON 保留现有认证、404/409/502/504 和输出处理，多行消息不重发已完成行。

同一调用可合并路由和实例方法的重复健康检查，但执行前仍核验实际容器。结果不确定时不重新按名字寻找新容器重发命令。错误日志仅记录服务器、命令类别、阶段、退出码和耗时；预期 Query 降级采用简短诊断。本次不重构全局 logger。

## Validation

- **镜像与选择**：GNU 命令名的两种布局；工具缺失、非 GNU、缓存失效及并发首次探测；真实 root/非 root 命令均不要求额外权限。
- **真实执行**：正常结果、非零退出、中文和特殊参数；普通查询管道超时、主命令忽略 TERM 时的 `-k` 行为；另外明确验证主动脱组/主命令提前退出的标准边界，不把边界测试写成全后代清理保证。
- **业务/API**：Query 成功、空列表、降级和双失败；RCON/消息权限、错误分类、顺序及不重复提交；取消、断线、容器替换与 Runtime 关闭。真实容器测试不能只用 SDK mock 替代。
- **资源与性能**：慢命令期间监控、健康接口仍可用，SDK 工作不遗留在已关闭资源上。交替比较完整旧/新路径的冷启动与热路径，Query/RCON 各至少 100 次，记录 p50/p95、失败率及 CPU，不删除慢样本。
- **定向回归与静态检查**：选择受影响调用路径及必要的快照/回档保护节点；运行 Pyright、Ruff 和受影响 Go 包检查，不运行本地全量套件。更新 API E2E 覆盖。

目标为健康 Query 热路径 p50 至少降低 50%、p95 不回退；确认约 100 ms 的等待台阶消失。该目标需要测量完整实现，不能把容器内 8–9 ms 当成端到端耗时。故障和负载测试在隔离环境执行。

## Risks / Trade-offs

- **镜像标签与工具名称变化** → 按运行实例探测，覆盖已用 GNU 8.30/9.7 的两种布局，缺少依赖明确失败。
- **GNU 比原 100 ms 轮询更精确** → 保留超时配置并记录失败率；是否调整阈值由独立实测决定。
- **原生工具不提供通用进程树回收** → 接受其公开边界，限定为现有 Query/RCON 命令，不把任意后台任务纳入这个适配器。
- **客户端取消或 Docker 故障不等于远端停止** → GNU 负责已启动命令的时间限制，Python 负责本地资源与错误报告；结果不确定时不重试写命令。

## Migration Plan

先实现工具选择与薄适配层，再接入两处命令入口并删除 Compose exec。保留 Compose 生命周期、快照、Restic、pidfd 和操作 journal 的代码不变；不修改线上镜像或安装包。没有数据库迁移或配置迁移，回滚应用镜像即可恢复原路径。

实现时同步 Minecraft、Runtime、monitoring、players、bot-integration-apis 文档及 E2E 覆盖；不将计划提前写入当前实现说明，不新增重复的 CLAUDE/AGENTS 文档。完成本地定向验证后 commit/push，等待最新 SHA 的自动 qualification，不重复手动触发。方案交付、研发、发布和线上部署分开进行。
