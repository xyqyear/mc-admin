# 调度、自检与外部集成

本页记录已实现的业务断言；执行结果以当前 SHA 的资格运行证据为准。
返回[覆盖索引](../coverage.md)，用例扩展遵循[架构与隔离约定](../architecture.md)。

| 功能域 | 稳定用例 ID | 已实现的验证内容 |
| --- | --- | --- |
| 定时任务配置 | `cron.configuration-and-weekdays` | 验证任务注册表、参数 Schema、受保护的系统任务、常用数字与名称形式的星期表达式；重复提交显式 ID 后完整列表仍只有一个任务，且名称与 cron 按新值更新；覆盖创建、读取、更新、暂停、恢复、取消，下次执行时间、筛选及非法输入。 |
| 定时任务校验错误安全输出 | `cron.safe-validation-errors` | 对创建和更新提交真实 Schema 布尔解析错误及 CronTrigger 未知值错误；保持 HTTP 400 和字符串 detail，公开已知字段/类型提示或未知适配器的固定中文错误，不回显提交标记。拒绝创建不产生任务，拒绝更新保留原持久定义与调度注册；应用文件日志和容器日志保留安全 ValidationError 类型诊断并排除提交标记。 |
| 调度注册与无效历史 | `cron.registration-and-invalid-history` | 停止独占部署后将 API 创建的任务改为未知类型和缺失参数；重启后列表与详情仍展示 active 期望状态及 failed 注册状态，系统任务仍正常 registered；通过公开更新修复后保留原 ID，暂停/恢复显示 inactive/registered，已注册任务重复恢复仍 409。 |
| 调度器真实执行 | `cron.execution-and-recovery` | 定时 Restic 备份生成真实快照和执行历史；暂停后不再继续执行；重启保留任务与历史；定时自检产生可查询的持久化结果。 |
| 调度操作上下文隔离 | `cron.creation-context-isolation` | 先登记失败备份、正常备份与系统自检，再通过真实建服任务创建自动重启计划；不再修改调度器，按公开 next-run-time 的错开时刻观察原有任务。每次执行拥有独立 cron 操作记录与准确终态，缺失路径备份保持 failed，不能被已成功建服的父记录覆写；成功备份只生成一个真实 Restic 快照，经公开恢复 API 验证原文件字节；自检具有关联的持久运行与实际健康发现，建服操作保持不变。 |
| 自检执行、事件流与历史 | `selfcheck.execution-history-and-stream` | 完整执行与流式执行的结果包含所有注册检查项；开始与结束事件、终态结果及持久化发现一致；验证单项执行、筛选、分页、状态与重启后的持久化。 |
| 游戏端口自检 | `selfcheck.game-port-current-state` | 对比 properties 中最终生效的端口赋值与 Compose 目标端口；制造不匹配并修复；检查当前状态替换、禁用检查项和历史保留。 |
| 模组元数据与所有权自检 | `selfcheck.jar-metadata-and-ownership` | 向真实部署上传构造的各类 JAR 元数据，不依赖文件名识别备份模组；Quilt 使用合法结构及小写 ID，并验证依赖 ID、截断或尾逗号文件不被误识别；检测所有权不匹配，并通过 API 修复。该用例验证元数据自检，不验证 JAR 被 Minecraft 加载。 |
| 备份自检 | `selfcheck.repository-health` | 配置真实 Restic 仓库；验证服务器快照覆盖与新鲜度、仓库访问、空闲锁状态，并核对相应自检发现。 |
| 依赖与文件系统恢复 | `selfcheck.dependency-and-filesystem-recovery` | 移除再恢复测试部署内可执行文件的执行权限，移走再恢复测试项目目录；对应检查项反映失败与恢复状态。 |
| DNS 禁用与配置校验 | `dns.disabled-and-validation` | 覆盖全部五个 DNS 路由，验证禁用时的状态与更新行为、匿名访问拒绝、非法供应商和地址配置；不访问云服务。 |
| DNS 受控网络边界与降级 | `dns.owned-edge-reconciliation` | 完整部署通过原始 DNSPod SDK 请求独占 HTTPS 协议服务，并使用真实固定镜像 MC Router；确认无变化零写入、单条路由 upsert、两侧 unknown 独立保留与部分更新、单目标失败后只补缺失记录、空期望和禁用保留实际状态。DNS 降级时服务器同步主操作成功，完整自检保留 warning/evidence 且其它检查继续，HTTP/自检结果/app.log/容器日志不泄漏合成上游错误。CA、hosts 与端口仅属于测试容器，不访问云账号。此用例验证网络协议边界，不替代真实供应商资格验证。 |
| DNSPod，需要显式选择 | `dns.dnspod-reconciliation` | 使用真实供应商及测试独占的 mc-router；独立 SDK 核对每条记录的唯一性、值和 TTL；验证启用状态、无修改的差异预览、A/AAAA/SRV 创建、幂等性、配置重载、路由偏差、地址与端口变化、CNAME 转换、部分删除及启用状态下的 DNS 自检；热禁用后生命周期触发不修改云端记录。 |
| 华为 DNS，真实云验证 | `dns.huawei-reconciliation` | 对真实华为 DNS 和独占 mc-router 验证记录增改删、CNAME 替换、独立 SDK 读取和权威 DNS 应答；非托管 TXT 保护记录必须保留；持久清单和独立回收程序验证云端清理。 |
| Minecraft 实际转发 | `dns.router-minecraft-traffic` | 普通回归不需要云凭据；使用真实 Minecraft 和 mc-router，通过唯一 MOTD 验证目的服务器、未知主机名拒绝、DNS 降级时路由修复。 |
| 华为 DNS 到 Minecraft | `dns.huawei-minecraft-connectivity` | 通过独立 SDK 和权威 DNS 核对华为云记录，从 SRV/A 应答取得端口与地址，经真实 mc-router 验证 Minecraft MOTD；包含首次递归解析、启动修复、创建/删除/同步自动触发、监听端口变化和停止服务器后保留记录。 |
| Mojang 真实访问 | `players.live-profile-and-skin` | 通过后端获取公开玩家资料和皮肤，要求成功解析身份、头像及更新时间；刷新皮肤，并在重启后保留下载缓存。 |

真实云 DNS 用例使用 GitHub Environment 中配置的现有公共 zone，纳入统一 API 不可变计划和全局 matrix。所有 API 分片使用无分支限制或保护规则的 `dns-e2e` 配置存储，provider 依赖选择所需私有配置和回收步骤，仅相应步骤接收凭据；不同依赖的 atomic group 可以同片。仓库只保留示例域名和配置指南。DNSPod 显式选择仍需提供 `E2E_EXTERNAL_CONFIG`。禁用 DNS、受控 HTTPS 协议服务或本地真实 mc-router 客户端测试通过，并不表示真实供应商的记录修改已经验证通过。

选择供应商前，应阅读[DNS 配置、资源归属与清理约定](../../suites/dns/README.md)。缺少所选供应商配置时，用例明确失败并给出可执行的错误提示，不会被标记为跳过或通过。Mojang 真实访问用例要求外部请求实际成功，仅收到“资料未解析”的响应不能通过。外部用例的实际运行结果以当前提交的相应 CI 运行及清理审计为准。

DNS 记录同步用例使用通过 API 创建、处于停止状态的 ACTIVE 服务器；另外的 connectivity 用例启动真实 Minecraft，验证配置域名经过代理到服务器的实际连接。DNS 验收同时要求华为云 API 记录正确、权威解析及首次递归查询成功；测试地址为运行器的回环地址，因此不验证互联网入口、防火墙或 NAT。各环境使用通用环境 ID 与可选相对父域组合为记录名称，避免并发同步互相覆盖。地址或服务器集合为空时，当前管理器跳过同步；因此部分删除场景保留一个目标地址，最终云端清理由独立供应商 SDK 按持久清单中的域名和范围执行，删除托管记录及测试创建的 TXT 记录，保留无关记录。SIGKILL 后应先回收本地写入者，再使用 `cloud/` 下无凭据的持久清单、当前凭据和 `cleanup-dns` 回收云记录；本地 Docker 回收不代表云端回收成功。
