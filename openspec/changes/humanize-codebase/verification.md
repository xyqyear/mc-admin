# Code-humanizer 实施与验证报告

审计基线：`a773bbe5e3f7787c180b115ac0c40ff61d1e675e`。实施分支：`refactor/code-humanizer-cleanup`。

66 项保留发现已实施，独立代理审查及修正循环已收敛。两个否决项保持原有业务边界：DM-05 不统一游戏与 RCON 端口扫描的不同失败政策；ST-07 不统一严格文件所有权与地图缓存的 best-effort 修复。逐项约束和原审查理由见 [reviewed-scope.md](reviewed-scope.md)。这里的“稳定”表示实施审查没有待修意见，完整交付仍取决于当前提交的部署验证与 GitHub 资格门禁。

## 主要结果

- 后端以 35 个具体类型的惰性资源和明确工厂取代字符串资源表与反射关闭。未初始化与禁用 `None` 分开，关闭只处理当前已构造实例；多应用隔离、取消、失败后继续清理及未确认写入者的恢复证据保留。
- 任务 DTO、有限数据库工作和 lease 登记只共享等价的现有协议。摘要仍不包含结果载荷，任务受理与完成分开，真正等待者在失败及释放后能继续写入。
- 删除无消费者的 Compose writer、聚合查询、配置 proxy 任意属性、旧 DNS/Cron 门面及重复 UUID/路径/DTO 解码。真实 HTTP、SDK、数据库和 CLI 契约保留。
- 前端以 54 个具体命名查询/命令 hooks 和普通下载 hooks 取代二级工厂。地图控制器返回 server/map/claims/players 四个具体分组，共用三个展示组件；维度、模式、视角、侧栏寿命和恢复/裁剪各自交互保留。
- Cron 零值与明确清空不再被旧草稿覆盖；目录覆盖决策一次应用到全部后代，目录外文件保持自己的决策；嵌套参数表单按 Enter 不会提前保存外层任务。
- 玩家有限资料流消费失败或没有终态的 EOF 显示重试，同时保留缓存与地图。上传、控制台、Cron、备份和通知的错误输出不公开敏感输入或原始适配器异常；原有状态码、部分结果、维护跳过及取消传播保留。
- CPU 采用每次新进程对象进行原有一秒线程采样，消除 PID 对象滞留。OCI 大层通过一 MiB 分块校验摘要和实际长度；小 JSON 校验、完整归档哈希和拒绝无效门禁的流程保留。

## 逐项处置

“完成”包括实现和独立代码复审，不代表当前提交的全部部署/远端门禁已经通过。TC-01/02/03 是已合并发现，分别由 RT-05/06 与 ST-08 的同一有效覆盖接住。

| ID | 保留修改 | 实施审查 |
| --- | --- | --- |
| RT-01 | 删除确认无消费者的内部入口与别名 | 完成，稳定 |
| RT-02 | 固定类型的惰性运行时归属，显式关闭当前资源 | 完成，稳定 |
| RT-03 | 任务 summary 统一字段，detail 只增加 result | 完成，稳定 |
| RT-04 | 共用有限数据库工作的取消传播协议 | 完成，稳定 |
| RT-05 | 并发测试验证同时进入和每任务独立结果 | 完成，稳定 |
| RT-06 | 只合并重复搭建，保留 receipt、类型和中间进度契约 | 完成，稳定 |
| RT-07 | 删除失实说明与机械叙述，保留语义说明 | 完成，稳定 |
| RT-08 | 共享登记与释放 lease 的具体生命周期 | 完成，稳定 |
| RT-09 | 共用状态纯投影和 terminal dismissal | 完成，稳定 |
| ST-01 | 共用玩家所属的 UUID 语法规范化 | 完成，稳定 |
| ST-02 | 删除确认无消费者的内部入口 | 完成，稳定 |
| ST-03 | 公共 typed chunk 操作取代跨类私有调用 | 完成，稳定 |
| ST-04 | 渲染队列声明真实双 cache 接口 | 完成，稳定 |
| ST-05 | 上传覆盖策略只解释一次 | 完成，稳定 |
| ST-06 | 归档使用已有 canonical confinement helper | 完成，稳定 |
| ST-08 | 仅替换高层 ownership mock 顺序 oracle | 完成，稳定 |
| ST-09 | 删除 Process 对象缓存，保留每次一秒线程采样 | 完成，稳定 |
| ST-10 | 上传错误公开原文必须作为独立修复 | 完成，稳定 |
| FE-01 | 将二级 hooks 工厂迁移为具体命名 hooks | 完成，稳定 |
| FE-02 | 删除已全仓确认无消费的手写导出 | 完成，稳定 |
| FE-03 | 统一玩家身份的 UUID 纯规范化函数 | 完成，稳定 |
| FE-04 | 复用同一 Minecraft→Leaflet 坐标 helper | 完成，稳定 |
| FE-05 | 区分 SSE 解析失败、handler 失败及玩家有限流终态 | 完成，稳定 |
| FE-06 | 先修 Cron 值错误，再类型化局部编辑状态 | 完成，稳定 |
| FE-07 | 复用地图页面的具体展示接线，保留业务组件寿命 | 完成，稳定 |
| FE-08 | 精简 Cron 参数表单 API，保留实际 renderer 策略 | 完成，稳定 |
| FE-09 | 共享最小路径树构造，保留三种树的交互差异 | 完成，稳定 |
| FE-10 | 缩小 FileIcon 输入，删除伪造 metadata 适配 | 完成，稳定 |
| DM-01 | 统一 finding 存储解码，查询形状保持 | 完成，稳定 |
| DM-02 | 移除测试专用 Compose writer，迁移真实 Docker 效果覆盖 | 完成，稳定 |
| DM-03 | 移除三个测试专用聚合入口 | 完成，稳定 |
| DM-04 | 删除两个无业务消费者的配置便利 API | 完成，稳定 |
| DM-06 | 按固定清单删除监控便利 API，保留 wire 和真实 source checks | 完成，稳定 |
| DM-07 | 删除六个确认无消费者的旧别名和 exports | 完成，稳定 |
| DM-08 | 移除任意名字 proxy，保留 typed owning view和generic manager | 完成，稳定 |
| DM-09 | 路由复用现有 user_to_public，原 guard保留 | 完成，稳定 |
| DM-10 | 真正触发 union guard，保留独立的项目边界 | 完成，稳定 |
| CN-01 | DNS 旧接口受控退役，保留现行 DTO | 完成，稳定 |
| CN-02 | 统一 planner record 类型时显式迁移字段顺序 | 完成，稳定 |
| CN-03 | 删除无生产需求的排时查询和pattern参数 | 完成，稳定 |
| CN-04 | 退役同步/自定义 fallback，仅保留 async/fixed-None | 完成，稳定 |
| CN-05 | 只保留显式 cron 注册入口 | 完成，稳定 |
| CN-06 | 删除确实未使用的供应商锁与操作映射 | 完成，稳定 |
| CN-07 | DNS 写测试必须检查实际外部 payload | 完成，稳定 |
| CN-08 | 实际 cron 调度测试等待持久终态 | 完成，稳定 |
| CN-09 | 独立修复 raw public/history/log 输出 | 完成，稳定 |
| E2-01 | 修复 E2E 配置与世界别名预期对象污染 | 完成，稳定 |
| E2-02 | 合并重复 full self-check，按创建ID验证历史 | 完成，稳定 |
| E2-03 | 过滤结果验证精确身份与数量一致 | 完成，稳定 |
| E2-04 | 统一当前候选的 task 等待循环 | 完成，稳定 |
| E2-05 | 只共享 multipart 编码，业务发送与断言留原suite | 完成，稳定 |
| E2-06 | 仅合并现有固定压缩工作量；撤回无测量的暂停方案 | 完成，稳定 |
| E2-07 | 空文件 oracle 区分缺失/null与真实空内容 | 完成，稳定 |
| CI-01 | 分块校验 OCI 层的长度与摘要，保留完整归档验证 | 完成，稳定 |
| CI-02 | 用标准深复制代替 JSON 往返 | 完成，稳定 |
| TC-04 | 地图fanout验证坐标与取消后的幸存成功 | 完成，稳定 |
| TC-05 | 完整 argv 观测即可，不再造测试用 CLI parser | 完成，稳定 |
| TC-06 | 子路径压缩验证实际成员与未选数据隔离 | 完成，稳定 |
| TD-04 | 并发玩家测试证明先创建再关闭 | 完成，稳定 |
| TD-05 | 删除无断言 empty smoke，先补实际配置替换 | 完成，稳定 |
| TD-06 | 皮肤 handoff 测试观察真实数据库结果 | 完成，稳定 |
| TF-02 | 独立修复 Cron 0/空串被旧闭包覆盖 | 完成，稳定 |
| TF-03 | 独立修复目录勾选完整集合丢更新 | 完成，稳定 |
| TF-04 | 补文件夹上传身份与实际 multipart 字节 oracle | 完成，稳定 |
| TF-05 | 保留上传生命周期替身，补真实 hash 与发布等待 oracle | 完成，稳定 |
| TF-06 | 退出测试触发真实清理路径，保留跨session隔离 | 完成，稳定 |

## 定向证据

本地执行只选择改动及受影响路径，未执行项目或组件全量测试，也未通过代理分片拼全量。以下按业务边界归纳，避免把多轮复验累计成独立测试总数。

| 边界 | 已通过的本地证据 |
| --- | --- |
| Runtime 与数据库 | 真正并行进入/每任务独立结果、None 缓存、未访问工厂关闭哨兵、独立 engine/session 覆盖恢复、多应用隔离、八个启动失败阶段、有限数据库取消、未知写入者证据保留及当前实例关闭。 |
| 归档与 lease | 真实 SQLite/API init/append/hash/受理后等待真实 ARCHIVE lease；父目录重定向后实际执行失败，原树和外部文件字节保持、引用/stage/上传临时文件清理、同 claim 可重获。另保留最终目标及受理前越界拒绝。 |
| 区块 CLI | 公共 replace/remove 执行器分别覆盖 error/missing result/wrong count/nonzero exit/成功，以及取消后实际子进程 PID 已消失，共 12 个变体；真实 mcmap/Restic 另 5 个保护、负坐标恢复/回滚及预览变体通过。 |
| 所有权 | 自有 root Docker 环境真实 stat/UID/GID/文件字节验证既有与缺失缓存目录；低层 chown、PermissionError、参数及 confinement 覆盖保留，两个不同修复政策未合并。 |
| Docker 配置及监控 | 最后 3 个真实 Docker 节点通过，无跳过；真实配置任务改变 MODE 与容器 ID，journal/源元数据/运行意图保持，监控取样成功，测试拥有的容器和网络全部清理。 |
| 上传与错误 | per-file/outer/preflight/session/部分字节/取消及安全作者消息的 10 个相关节点通过；真实 HTTP 玩家资料 SSE 验证缓存事件、安全终态、其它 fetch 的取消排空和数据库 session 关闭。 |
| Cron 与连接服务 | 实际模型/CronTrigger 安全诊断、真实 Restic 保留清理/通知/取消、真实 APScheduler 同执行 ID 的持久终态、受管重启 ID、SDK 完整 payload、慢批次旧客户端排空及 DNS/router 独立失败恢复。 |
| 前端输入与身份 | 受控 Cron 外部 props/草稿/无效数字/raw↔visual 和真实保存请求；实际目录对话框及 FormData 传输字节；canonical UUID 缓存/在线过滤；负坐标、512/16 网格及洞环、跨维度延迟 pan 和选区重置。 |
| 地图展示 | 两个真实 screen/controller/query/selector/MapInitDialog 的 12 个不同节点全部通过：加载、导航、错误/空世界、初始化三种原因、force=false 请求及两页原有状态错误可见性差异。 |
| 有限流/哈希/身份会话 | 消费者 Error/SyntaxError 传播与 reader 释放、资料重试恢复缓存；真实 hash-wasm 固定 abc 摘要、同长度错误/无摘要、100% 非终态、断线重连/失败/取消/卸载；真实 HTTP 401、退出再登录及迟到旧观察者不影响新缓存。 |
| E2E 驱动与发布 | 七个明确 Go race 节点、受影响包 vet、真实 HTTP 反例和 multipart 字节、精确搜索/快照 ID、压缩原种子与 260000 entries；发布拒绝/真实 OCI tar 的 33 个筛选案例及部署演练的 6 个指定案例。 |
| 异步异常装饰器 | 安全修复先独立提交 `896b9ec`，async/fixed-None 简化后 22 个保留/新边界节点及 3 个实际消费者节点通过；独立确认 16 个生产消费者均 async，另外两项 metadata/取消复验通过。 |

独立实施审查由不同作者代理完成。后端三轮关闭了 UUID 边界、真实区块子进程协议、等待者释放、未构造资源关闭、归档执行期复检及缓存说明的缺口；前端第二轮补齐受控输入、真实身份/坐标/controller 和公共展示证据；E2E 审查修正 catalog ID 非空/唯一断言后稳定；装饰器和新增部署案例另行复审。没有通过降低断言、改变超时或删除有效业务覆盖取得通过。

## 静态与构建

- 后端：`uv run ruff check .` 通过；`uv run pyright` 为 0 errors、0 warnings。
- 前端 Node 24：`pnpm lint`（含导入边界）、`pnpm typecheck`、`pnpm build` 全部通过。生产构建仍报告既有大 vendor chunk 提示，构建成功。
- Go：明确受影响包的 vet、指定 race 节点和当前 runner 构建通过；browser 新旅程 ESLint/严格类型检查通过。
- OpenSpec：12 份主规格及此 change 的严格校验通过；新要求合并保留原条文，零间隔起点允许既有等价 `*/n` 规范形式。
- 当前启用工具中没有 IDE diagnostics；代码诊断使用上述 Ruff/Pyright/ESLint/TypeScript，不声称执行了不可用工具。

## 两项量测

CPU 构造在同一自有解释器上五轮、每轮 10000 次，原 eager-default cache 与新对象的中位成本为 6.73/6.90 微秒；没有证据证明原 cache 有有意义的收益。一秒 blocking 样本不依赖跨调用非阻塞基线，NoSuchProcess 归零、AccessDenied 传播、多核 175% 与事件循环可响应的契约由定向案例保留。

OCI 同一 100669440-byte 层 fixture 在两个独立进程的 manifest/config/archive 哈希完全相同。原/流式 peak RSS 为 118992/23248 KiB，Python allocation peak 为 100758876/3236569 bytes。这只描述该 fixture 和环境，没有宣称普遍性能倍数或已证明实际 OOM。

## 部署与交付记录

首次干净候选 `af6d226f373728d746cf0d31655a10604ad05f9a` 的四个新增 API 案例中三个通过，控制台案例的安全错误/真实 stdin/RCON/正常关闭/健康断言通过，但故障注入的 `none` 日志驱动未恢复，导致 runner 原有诊断阶段失败。因此整次 API run 严格保留为失败；四个 owned 环境仍全部完成清理。修正只在用例首次变更前登记真实配置恢复、任务终态、健康及日志可读性清理，不降低业务断言、诊断或超时。

同一初次候选的新增目录上传 browser 旅程真实通过（1 test），官方候选 evidence 的 owned cleanup 完整。它是初次 SHA 的局部证据，不能替代修正后干净候选的验证。

修正后干净源码 `76e0ab56e802e72f6987b66e40f43f8a42c8d49e` 的候选已通过四个新增 API 案例 normal/no-reuse 各一轮与实际目录上传 browser 旅程。构建前、构建后及执行后官方 source 记录完全一致，dirty=false。故障恢复经过第二轮独立复审，配置文本相等仍验证真实容器；初始任务只有完整成功解析后才确认终态，网络/解码/超时不被吞掉。

| 候选绑定 | 值 |
| --- | --- |
| 源码 fingerprint | `sha256:09c262e0e80da2b31528315dce4c5a99dfd6e68a7e4dd01c87ff5181986ed104` |
| OCI manifest | `sha256:99ed4d2b66d7a6acd345bfadadbb5e4a38af2cc04d094ac6b1549180004ec2cf` |
| Docker/config image ID | `sha256:1eb1a7682377f41b64a2ec7f09930e9b6e02e70666c51142cf16078a2a960c97` |
| OCI archive SHA256 | `sha256:2f08628dcacd40f95aae46f641b73d1ecd44389fdbba91505f5162d7788da6a7` |
| Runner SHA256 | `sha256:b2ed8f1f814cb332e4f7a688a5aa4c9d5e23fdcd9911ae2232ae0b63a7380feb` |

| 部署案例 | normal | no-reuse |
| --- | --- | --- |
| archive.subpath-compression-content | passed | passed |
| files.multipart-safe-failures | passed | passed |
| cron.safe-validation-errors | passed | passed |
| minecraft.console-safe-adapter-errors | passed | passed |

两轮独立 coverage 均为 selected/recorded/passed=4/4/4，selected_cases_complete、all_selected_cases_passed、shards_complete 三个实际字段均 true；missing_case_ids、missing_shard_indexes、missing_trace_case_ids、run_errors 均为空。未把两轮重叠案例合并成 exact-once 结果。目录上传 browser 为 1 passed，unexpected/flaky/skipped 均为零。

三个官方 runtime evidence 都绑定上述 clean source/config/OCI，owned_cleanup_complete=true；九个 owned 环境的 manifest 全部 cleaned=true，对应容器与 Compose 网络实际为零，自有 builder/container/state volume 已删除。保存的两次候选及初次失败证据未删除，未操作他人资源。浏览器仅将原生选目录 FileList 接入生产 document drop fallback；File、相对路径、字节、对话框、策略、HTTP 和宿主文件均保持真实。

本地证据目录：`/tmp/mc-admin-humanizer/final-deployed-76e0ab56-20261006`；完整说明 `/tmp/mc-admin-humanizer/final-deployed-verification.md`。这是已验证代码提交的本地定向证据，报告入库后仍需对最终提交执行完整远端 qualification。

待完成：推送最终提交，以 publish=false 触发完整 `Qualify and Publish Application`，统一审计同一 SHA 的 candidate/Go、static/frontend、全部 backend 分片/覆盖、全部普通及 Huawei API E2E/覆盖/清理、全部 browser 分片/覆盖与最终 qualification。普通 push 检查与旧 SHA 绿灯不能代替。

最终证据以本报告的后续交付记录和 GitHub qualification artifacts 为准。当前尚不宣称完整交付通过。

代码与文档总差异：360 个文件，增加 9,139 行，删除 6,183 行（相对审计基线，包含实现、测试、规格和报告）。
