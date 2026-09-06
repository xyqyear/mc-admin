# API E2E 验证记录

验证日期：2026-09-06（Asia/Shanghai）。当前目录包含 **62 个场景：59 个常规回归用例（其中包含 13 个冒烟用例），以及 3 个需要显式选择的外部服务用例**。本轮复核与上一轮验收分别记录，不能合并不同镜像的运行来声称全部通过。DNSPod／华为 DNS 云端变更仍缺少专用测试域名凭据。

## 缺陷复核后的验证

- 应用：仓库 Dockerfile 构建的 `mc-admin:e2e-reviewed-labels`，`sha256:8ba6943c76c6de61f6f0c52462bde3211c57222b83fc9be53557bb2c4aa979b6`，包含 Docker 标签修复及生产默认 Uvicorn INFO 日志。
- 新增 `archive.task-permissions`；增强真实登录日志、审计配置、Quilt 元数据、Linux 文件名兼容性及带等号 Docker 标签的生命周期断言。缺陷判定、修复范围及保留策略见[缺陷复核记录](defect-review.md)。
- `e2e-reviewed-labels-no-reuse`：当前 `8ba6943c…` 镜像，种子 20260909，**6/6 通过**；6 个独立环境全部清理。覆盖任务鉴权、真实登录日志、审计配置、Quilt、Linux 文件名和含等号标签的 Minecraft 生命周期；没有通过复用前一场景状态获得成功。
- `e2e-reviewed-final-no-reuse`：标签问题发现前的 `04dd55f1…` 镜像，种子 20260909，5/5 通过，5 个独立且已清理的环境。选择为 `archive.task-permissions`、`auth.code-login-and-csrf`、`system.audit-redaction`、`selfcheck.jar-metadata-and-ownership`、`files.directories-search-and-errors`。
- 后端组合检查：`uv run python -m pytest tests/files tests/archive tests/background_tasks tests/dns tests/self_check tests/players tests/test_audit_redaction.py tests/test_log_monitor.py tests/test_tasks_auth.py tests/test_tasks_router.py tests/test_auth_session.py tests/test_login_code_logging.py tests/test_audit.py tests/test_docker_ps.py -q -o addopts=`，**584 通过、2 个原有跳过项、2 条原有弃用警告**。包含真实固定版本 mc-router 客户端集成。
- 完整 Pyright：0 个错误、0 条诊断警告；工具另有版本更新提示。`make check` 的 Go vet 和 race 测试通过，包含截断票据日志识别及脱敏测试。

当前应用镜像上的完整回归结果：

| 运行标识 | 选择与并行配置 | 结果 |
| --- | --- | --- |
| `e2e-reviewed-labels-shard-1` | regression，分片 1/3，种子 20260908，2 workers／1 Minecraft slot | 28/28 通过；24 个环境；4 个用例复用环境 |
| `e2e-reviewed-labels-shard-2` | 同镜像、目录和种子，独立并发分片 2/3 | 16/16 通过；16 个环境；未复用 |
| `e2e-reviewed-labels-shard-3` | 同镜像、目录和种子，独立并发分片 3/3 | 15/15 通过；15 个环境；未复用 |

合计 **59/59 通过，没有遗漏或重复用例，没有运行级错误**。三个分片及 6 个禁用复用重点用例使用同一静态二进制，SHA256 为 `6102f6a8aeeed63f602a842e124a4cc37da5fda0b4e52bd457eb4f800634646a`。完整回归的 55 个环境和重点复测的 6 个环境均标记已清理，运行时目录无残留；Docker 复查没有带 E2E 运行标签的容器，也没有 `e2e-` 前缀网络。之前显式中止的各轮环境亦已清理。镜像缓存和端口锁文件按设计保留。

各分片的主要运行参数为 `--backend-image mc-admin:e2e-reviewed-labels --minecraft-image itzg/minecraft-server:java25-e2e-local-vanilla-1.21.11-64bb6d763bed --tag regression --shard N/3 --seed 20260908 --workers 2 --mc-slots 1 --timeout 45m`，其中 N 分别为 1、2、3。重点复测另外使用 `--no-reuse --seed 20260909` 并精确选择上述六个用例；它不是一次完整 59 用例的禁用复用运行。

报告位于 `/tmp/mc-admin-e2e-regression/e2e-reviewed-labels-*`。合并检查通过以下命令执行并通过：

```bash
./bin/mc-admin-e2e coverage --require-complete --require-observed \
  --output /tmp/mc-admin-e2e-regression/e2e-reviewed-labels-coverage \
  /tmp/mc-admin-e2e-regression/e2e-reviewed-labels-shard-1 \
  /tmp/mc-admin-e2e-regression/e2e-reviewed-labels-shard-2 \
  /tmp/mc-admin-e2e-regression/e2e-reviewed-labels-shard-3
```

当前部署的 **154 个 API 操作（151 HTTP/SSE、3 WebSocket）均有用例访问记录，150 个观察到成功响应，0 个未访问**。四个只有拒绝／其他错误响应的操作仍是 `GET /api/dns/records`、`GET /api/dns/routes`、`GET /api/dns/status` 和 `POST /api/dns/update`；它们的云端成功行为未验证。报告不计入环境准备流量，操作访问也不代表所有业务分支已覆盖；完整中文对应清单见[覆盖清单](coverage.md)。

两个跳过项是 `tests/dns/test_api.py` 中原有的 `test_get_dns_records_client_not_available` 和 `test_get_router_routes_client_not_available`，均模拟“已初始化但内部客户端为空”的状态。源码已有显式 skip 标记；本轮未把它们计为通过，也未新增跳过规则。

| 失败／修复证据 | 结果及范围 |
| --- | --- |
| `e2e-task-auth-red`，旧集成镜像 `953685ef…` | 实际运行中的压缩任务允许匿名取消，返回 200；新增用例按 401 预期失败 |
| `e2e-sys-code-logs-before`，上一轮验收镜像 `0bf2fc78…` | 真实登录后普通日志含 code，审计含 ticket，新增断言失败 |
| `e2e-reviewed-no-reuse`，中间镜像 `96ee17e5…` | 4/5 通过；登录日志断言发现 Uvicorn DEBUG 的 WebSocket 凭据输出，不能记为全部通过 |
| `e2e-sys-code-transport-before`，中间镜像 `96ee17e5…` | 增强断言进一步检测到 code、截断 ticket 及凭据帧；该次保存的诊断已对可见片段脱敏 |
| Quilt／router 专项修复前后 | 修复前 6 失败／44 通过；修复后 50 通过。真实 router 重复删除在修复前失败、修复后通过 |
| Linux 文件名修复前后 | 字面反斜杠文件名在修复前被 400 拒绝；修复后 files 专项 113 通过，并通过真实 API 验证 |
| Docker 标签解析修复前后 | 新增专项在原代码上 5 失败／5 通过；修复后连同既有 Compose 测试 26 通过。同一份真实 CLI 输出在原解析器中失败、修复后成功解析，健康状态判断恢复为 true |

中间镜像的 `e2e-reviewed-shard-1/2/3` 因 Minecraft 安装 JAR 下载超时、连接重置或响应提前关闭而停止；退出容器仍被等待 healthy，随后显式发送 SIGTERM 回收这些测试运行。对应结果包含未执行或中断用例，保留为失败记录。缓存 Docker 镜像并不等于每个新 data 目录已有游戏 JAR；此处没有将环境下载故障归因于任务鉴权修复。

后续回归使用显式 `--minecraft-image itzg/minecraft-server:java25-e2e-local-vanilla-1.21.11-64bb6d763bed`，通过上游支持的本地 JAR 启动模式运行同版本真实游戏服务：

- 依赖镜像 `sha256:472dbd2055ca17fe59ded9629997a0d7566ea0d93a6fe0e9d4f7448a756b03aa`，继承原固定 itzg 镜像 `59feb0a1…`。
- 官方 Minecraft 1.21.11 JAR 为 56,327,581 字节，SHA1 `64bb6d763bed0a9f1d632ec347938594144943ed`，与官方版本元数据匹配；本地 SHA256 为 `f83b8e093865806f931c7e34aae41b177d4c076335263dd124c75d6d65dd1726`。宿主和独立 Docker 下载探测均通过校验。
- 包装仅匹配 VANILLA 1.21.11，缺少 JAR 时先复制已校验文件，再设置 `TYPE=CUSTOM`、`FAMILY=VANILLA`、`CUSTOM_SERVER=/data/minecraft_server.1.21.11.jar`，执行原始 `/image/scripts/start`。其他版本和类型沿用原启动方式。这是[上游支持的本地 JAR 模式](https://github.com/itzg/docker-minecraft-server/blob/master/docs/configuration/misc-options.md#running-with-a-custom-server-jar)，没有使用模拟 Minecraft。
- 独立容器在 `--network none` 下实际启动 Minecraft 1.21.11，日志到达 Done，RCON `list` 成功。它验证真实游戏行为，但不验证 `install-vanilla` 的在线元数据／下载步骤；游戏进程仍可能尝试访问外部认证服务。
- 制备文件与校验记录位于当前主机 `/tmp/mc-admin-e2e-minecraft-network/{Dockerfile.offline,entrypoint-offline.sh,verification-offline.json}`。项目默认 Minecraft 镜像保持原设置；该临时标签仅存在本机，没有发布到上游仓库。

先前仅预放 JAR 的缓存镜像 `47c51645…` 完成过单个 `minecraft.lifecycle` 冒烟验证（`e2e-reviewed-cached-minecraft-smoke`），但完整回归仍遇到在线安装器的元数据／下载故障。其最初本地别名 `mc-admin:e2e-minecraft-cached` 还在 `e2e-reviewed-final-shard-1/2/3` 被既有的 itzg 镜像名称校验拒绝，属于测试输入配置错误；改用合法本地别名后的 `e2e-reviewed-qualified-shard-1/2/3` 因在线依赖故障中止。这些结果保留为失败记录，没有放宽应用的镜像校验。

`e2e-reviewed-local-jar-shard-1/2/3` 使用 `04dd55f1…` 应用和 `472dbd20…` 依赖后，进一步复现了独立的后端标签解析问题：Docker 已 healthy，标签值 `CUSTOM:FAMILY=VANILLA` 使原解析器抛出 ValueError，应用始终返回 RUNNING。这轮显式中止并保留记录；真实 Docker 输出与原代码复现保存在 `/tmp/mc-admin-e2e-label-review/`。上表的最终验证使用重建后的 `8ba6943c…` 应用镜像。

## 上一轮验收记录

以下记录属于复核修正之前的 61 个场景和原镜像：58 个常规回归均通过，真实 Mojang 服务验证通过。它们保留历史证据，不替代当前代码的验证。

### 部署与可执行文件

- 源码基线：`da30f4b033a386dc97ea72254e3ec0a4b0bdab1f`，叠加本次实现工作区中的 E2E 用例及已复现问题的生产代码修复。
- 最终应用：使用仓库根目录的 Dockerfile 构建，标签为 `mc-admin:e2e-qualified`，镜像为 `sha256:0bf2fc7834bdbdc49da6c727a9ef9dd13efb6ca39a694ca0db124e05c1d9ee46`。
- 较早的集成验证／禁用复用验证镜像：`mc-admin:e2e-final-regression`，`sha256:953685efa7a0a4726b47484431fbda2c25e9293801dca3c63c40945cec6cb7b5`。该镜像仅缺少最后一次针对完整字段名的审计脱敏修复。
- Minecraft：`itzg/minecraft-server:java25@sha256:59feb0a1ef286f20a20560c56adf5b927155bfa842951f5db8b8bbc5a1a3ebde`，游戏版本为 `1.21.11`。
- 环境：Linux/WSL，本地 Docker Engine `27.3.1`，Go `1.27.1`。应用镜像提供 Compose、Restic、fd、mcmap、7z 及 Python 依赖。
- 发布用可执行文件：通过 `make build` 构建，使用 `CGO_ENABLED=0`，已确认采用静态链接。该静态可执行文件也通过了专项真实 API 验证。工作区中的场景验证使用同一份源码构建的 Go 程序。

### 真实回归与外部服务验证结果

| 运行标识 | 用例选择与模式 | 结果 |
| --- | --- | --- |
| `e2e-qualified-shard-1` | 最终镜像，回归分片 1/3，种子 20260907 | 27/27 通过；23 个环境；4 个用例复用了环境 |
| `e2e-qualified-shard-2` | 相同镜像、用例目录和种子，并发运行分片 2/3 | 16/16 通过；16 个环境 |
| `e2e-qualified-shard-3` | 相同镜像、用例目录和种子，并发运行分片 3/3 | 15/15 通过；15 个环境 |
| `e2e-final-no-reuse` | 较早的集成镜像，当时完整的 57 个回归用例，种子 8675309，3 个并发工作单元，1 个 Minecraft 环境并发名额 | 57/57 通过；57 个独立环境；未复用环境 |
| `e2e-minecraft-scheduled-normal`, `e2e-minecraft-scheduled-no-reuse` | 集成镜像上新增的定时重启用例，种子 65001/65002 | 两次均通过；验证了真实调度执行、容器重启、健康状态下的 RCON 以及游戏数据保留 |
| `e2e-sys-audit-aliases-before` | 较早镜像上增强后的审计用例 | 预期失败：真实审计日志暴露了 `ak`、`sk`、`code` 字段中的凭据；测试程序未打印凭据值 |
| `e2e-sys-audit-aliases-after`, `e2e-sys-audit-aliases-noreuse` | 最终镜像上修复后的审计用例，常规模式与禁用复用模式并发运行 | 两次均通过；完整字段名 `ak`/`sk`/`code` 被脱敏，公开的任务／状态字段得到保留 |
| `e2e-qualified-mojang` | 最终镜像，显式选择真实 Mojang 资料／皮肤用例 | 1/1 通过；成功解析身份、获取皮肤／头像并持久化缓存 |
| `e2e-static-qualified` | 最终静态可执行文件与最终镜像，登录码登录和审计用例，禁用复用 | 2/2 通过 |
| `e2e-world-ci-user2` | 接近 CI 的 UID/GID 1001，具备 Docker 用户组访问权限，并使用独立 Docker 配置 | 旧版格式提取、全部四种范围的恢复／回滚均通过 |
| DNSPod／华为 DNS 云端用例 | 已实现，需要显式选择 `external,dns` | 尚未针对云账号执行；缺少必要的测试域名配置 |

最终三个分片合并后为 **58/58 通过，没有遗漏或重复用例**。完整的禁用复用运行覆盖了较早的 57 个用例；新增的定时重启用例和增强后的审计用例各自另行完成了禁用复用验证。这些是不同运行的记录，不能据此声称全部 58 个用例曾在最终镜像上的同一个禁用复用进程中执行。

报告保存在当前主机的 `/tmp/mc-admin-e2e-regression/`；非 root 用户的世界用例报告位于 `/tmp/mc-admin-e2e-world-ci-user/`。这些是运行生成的证据，并非提交到仓库的测试数据。最终运行报告中没有运行级错误，所有环境均标记为已清理，运行时子目录也已删除。运行后的 Docker 检查未发现残留的带 E2E 标签的容器。可复用镜像和端口锁文件按设计保留。

### API 访问覆盖核查

`e2e-qualified-coverage/coverage.json` 和 `coverage.md` 由最终三个分片的结果通过 `coverage --require-complete --require-observed` 生成。

- 已部署 API 共 **154 个操作**：151 个 HTTP/SSE 操作，以及 3 个 WebSocket 路由。
- **150 个操作**在已通过的用例中观察到了成功响应。
- **没有操作**缺少场景访问记录。
- 尚未观察到成功响应的四个操作是 `GET /api/dns/records`、`GET /api/dns/routes`、`GET /api/dns/status` 和 `POST /api/dns/update`。常规回归验证了它们在未启用服务时的行为及错误响应；真实服务提供方的成功行为需要配置并运行外部 DNS 用例。

采集器排除环境准备流量，将拒绝响应、其他状态响应和失败用例中的访问记录分别保留；支持挂载后的 API 路径前缀及 `{z}.png` 这类参数后缀，并核对镜像、Schema、用例目录的一致性，以及分片和用例结果的完整性。仅包含 Mojang 用例的局部报告已被 `--require-observed` 正确拒绝。操作访问记录不能证明所有输入、分支或行为均已覆盖；详见[功能与用例对应表](coverage.md)。

### 当时的修复与检查结果

原始真实场景直接证明了登录用户越出数据目录读取文件、压缩取消终态后仍有输出、审计记录测试秘密、Quilt 元数据自检漏报及玩家日志跟踪异常。其他文件入口来自共同根因排查和修复后验证；玩家筛选有原实现与真实 SQLite 对照；子进程生命周期有原辅助函数隔离复现；mc-router 使用真实固定版本容器做客户端集成。它们具有不同的证据层级，不能统称为每条路径都由原始真实 E2E 独立复现。具体影响边界、修复取舍及未解决场景见[缺陷复核记录](defect-review.md)。

- `make check`：Go vet 检查通过；框架及领域测试辅助组件的测试在开启竞态检测时全部通过；Go 代码格式检查通过。
- `uv run python -m pytest tests/files tests/archive tests/background_tasks tests/dns tests/self_check tests/players tests/test_audit_redaction.py tests/test_log_monitor.py -q -o addopts=`：**519 个通过，2 个原有跳过项，2 条弃用警告**。
- 完整后端 Pyright：**0 个错误，0 条警告**。
- E2E 工作流：actionlint `1.7.12` 检查通过。两个 OpenSpec 变更均通过严格校验；差异空白检查通过。
- 当前没有可用的 IDE 诊断连接器；实际使用的代码诊断工具为 Go vet 和 Pyright。

此前的框架验证还包括：13/13 冒烟用例在允许复用和禁用复用时均通过、独立分片并发运行、普通用户清理、Minecraft 环境准备过程中收到 SIGTERM，以及 SIGKILL 后基于资源日志、可重复执行的清理恢复。这些记录仍保存在 `/tmp/mc-admin-e2e-runs/` 和 `/tmp/mc-admin-e2e-nonroot-runs/`。

GitHub Actions 工作流已通过静态检查，其部署、分片和报告机制也已在本地执行验证，但尚未从本工作区在 GitHub 上运行。SIGKILL 后的外部 DNS 云端清理需要使用已记录的生成域名范围和提供的测试账号；本地 Docker 清理成功不能证明云端也已清理。浏览器交互，以及文档所列的组合条件和长时间运行边界，仍不在本次 API 验证范围内。
