# 后端测试业务审查：根目录与外部边界

审查范围：backend/tests 根目录 test_*.py，以及 dns、events、migrations、contracts、architecture、testing、ci、support、fixtures。静态审查，未运行测试、未改仓库。判断依据为业务输入、结果、副作用、失败恢复、资源所有权；不以 mock 数量或断言数量判断测试价值。以下“修改”不代表删除已有不变量。

## 首要结论

1. 鉴权应通过真实数据库用户、真实密码哈希和真实登录建立会话。当前 auth/session、tasks/auth、console 各自 mock 会话查询，失效账号、权限变化和密码错误路径容易断开。
2. events websocket 的 SQL 查询和总线订阅均被替换，当前主要证明路由把假数据重新编码。使用真实聊天持久化与真实总线，检查 replay/live 交界去重、游标顺序、断开退订。
3. 日志监控前半测试 fake 真实可用文件 I/O，后半已有真实 tmp_path/轮询事件门范例，应统一。解析器纯函数案例验证实际日志语法和防伪造，不能一概判为过度测试。
4. DNS 真实云 API 不适合普通测试；外部状态 adapter 可保留。但 manager 的数据库和配置应真实，外部 SDK 序列化/分页/完整性契约独立保留，删掉重复的构造器字段和纯调用转发断言。
5. populate 末尾两个 submit_durable mock 测试是明显编排镜像；把 task_id、task_type 观察并入真实任务 API 流程，在真实终态后检查文件、源档案和持久记录。
6. 迁移真实 SQLite/发布快照、发布审计、安全脱敏、架构依赖约束是独立可观察约束，整体值得保留；不要以“直接断言 schema/调用”名义机械删除。
7. capability_guard 当前仅阻挡 Docker/已知二进制，未阻止未声明外部 socket/network。应允许 loopback/owned Unix socket 和显式 external opt-in，默认拒绝外网；保留真实本地 HTTP/子进程测试。

## 逐文件决策：根目录

| 文件 | 决策 | 业务理由和动作 |
| --- | --- | --- |
| test_adapter_error_logs.py | 修改 | 无泄漏及错误可诊断应保留；端口扫描两个实例可用真实 Compose 文件，mcmap 无效协议可用受控真实子进程，故障输出不应依赖真实第三方自然产生。 |
| test_async_fs_resolve_inside.py | 保留/小合并 | 真实路径、符号链接、批量顺序与逃逸边界有效；孤立异常继承断言可并入实际越界失败。 |
| test_audit.py | 修改 | 使用真实 Request 替换 MagicMock；至少一条真实 HTTP 请求→审计文件验证记录决策、脱敏、业务请求体不被耗尽；默认配置字段仅保留安全相关项。 |
| test_audit_redaction.py | 保留 | 独立表单/JSON/重复键/大小限制/精确词与子串边界保护凭据；可共用真实 middleware fixture，不必删掉不同输入格式。 |
| test_auth_session.py | 重写 | 真实 DB 用户、密码、登录 cookie、被删除/复用 id 用户、实际变更请求的 CSRF；当前成功 CSRF 请求 405 只证明到达路由，不证明受保护业务变更成功。 |
| test_compose.py | 保留/合并 | 各类实际 Compose 输入和兼容格式是解析契约；可参数化重复 YAML，不将每字段默认值等同业务。 |
| test_compose_file.py | 修改 | 保留端口/卷/environment 语法与持久化；独立 helper 与展开重复例合并，以完整 Compose 输入→可用配置/保存读取为主；用 tmp_path。 |
| test_config_binary_paths.py | 修改 | 创建真实可执行文件并设置隔离 PATH，替代 shutil.which mock；fallback 路径可注入，配置优先级有效。 |
| test_config_directory_paths.py | 保留 | 真实文件、环境、cwd、symlink 验证配置来源和路径绑定，避免运行目录改变后访问错误资源。 |
| test_create_server.py | 修改 | 已用真实 Runtime DB、真实 Compose 落盘；统一公共 DB/client，创建成功后新会话验证注册/配置，端口边界使用独立真实 socket 占用场景，保留冲突无副作用。 |
| test_decompression.py | 保留/收敛 | 真 7z/真实文件与发布失败保全非常有价值；进度测试保留可控制进程门，但不固定 27 等内部映射百分比，断言中间 0<进度<100 且未发布，终态内容正确。重复 stream/基本解压快乐路径合并。 |
| test_docker.py | 修改 | 真实两个 Minecraft 连接、玩家/聊天、隔离有效；固定 sleep(1) 替换有期限条件观测，两个客户端必须 finally 断开；避免同次读取 logs 当作永远无延迟。 |
| test_docker_ps.py | 保留/收敛 | Docker 命令输出解析边界可 mock，保留 =/空标签/健康语义；去掉与业务无关的逐字 CLI 参数断言或集中为单一适配协议测试。 |
| test_execution_observation.py | 保留/修改 | 101 条持久恢复任务、TTL、关闭事件和无文件扫描是真业务；统一 DB/config fixture，手工保留历史元数据需明确是恢复状态构造，正常任务通过公开 submit 入口。 |
| test_grid_geometry.py | 保留 | 邻接、孔洞、边界简化是实际几何契约，独立预期并非镜像实现。 |
| test_identity_runtime.py | 保留 | 真实不同数据库/签名密钥，角色更新和跨 Runtime 隔离有效；专用多 Runtime DB 是合理统一设施例外。 |
| test_instance.py | 保留 | 非 Docker 真实目录和独立 owned Docker 生命周期覆盖两种边界；磁盘空间断言保持合理范围而非平台固定值。 |
| test_log_exception_decorator.py | 保留/合并 | 异常传播、取消关闭、敏感参数不可格式化有效；函数 metadata/Logger 获取纯结构项可合并，勿删除取消与 BaseException 区分。 |
| test_log_monitor.py | 重写前半 | fake aiofiles.open/exists/getsize/seek/tell 和 create_task 断言替换真实日志追加、截断、删除重建、停止后不再处理；保留后半真实文件案例及事件同步。 |
| test_log_parser.py | 保留/参数化 | 输入日志样例→领域事件，聊天伪造 UUID/join/stop 防护有意义；减少同格式重复样例，保留 IPv6、模组日志、中文与异常字段。 |
| test_log_rotator.py | 保留 | 真 logger+gzip，旧消息归档和新消息留存是用户结果。 |
| test_login_code_logging.py | 保留/增强 | 传输失败故障注入合理；代码值不泄漏和 mapping 清理有效。增加真实 WebSocket 收到码→一次登录/过期拒绝路径，避免仅有 send_json 假调用证明身份业务。 |
| test_monitoring.py | 合并 | 各 getter 与 all_apis_integration 大量重复 smoke；保留一条真实容器采样生命周期和不存在容器失败，用负载/活动前后计数验证有意义变化，删掉重复计算 sum 的断言。 |
| test_monitoring_parsers.py | 保留 | 独立采样文本到明确数值及 malformed 行行为，避免依赖实时系统负载，不能与 Docker smoke 互相替代。 |
| test_operation_errors.py | 保留/小修改 | task/public error/private cause 边界有意义，注入错误合理；独立 manager 统一生命周期关闭，正常路径不用 fake 业务服务。 |
| test_populate_integration.py | 修改+合并 | 保留创建→上传→受理→终态→文件真实 7z 全流程；删除末尾 TestPopulateEndpointIsolated 的两条提交镜像并把有价值响应契约并入真实流程；统一 polling/helper/DB，移除随机端口依赖。 |
| test_process_resources.py | 保留 | 真实进程存活/退出，人工 AccessDenied/PID reuse/thread gate 故障合理；固定 interval==1 属内部参数，可改为循环未阻塞且多核百分比不截断。 |
| test_runtime.py | 保留 | 多应用真实隔离、取消、关闭顺序、未确认 writer 保留产物均是业务安全；故障注入资源关闭 spy 合理，不能批量取消。数据库专用 override 测试归设施。 |
| test_safe_errors.py | 保留 | 真 HTTP、真实 SQL，隐私和结构错误响应独立于实现，覆盖有效。 |
| test_spa_fallback.py | 修改 | 一个 / 根页面烟测弱，应实际未知前端路由返回 index，/api 未知路径保留 API 404，静态不存在资源不错误变成 HTML。 |
| test_startup_migrations.py | 保留 | 真空库/无版本库/升级数据保全，启动迁移业务边界完整。 |
| test_task_stream_shutdown.py | 保留 | 真 Uvicorn 进程与 socket，SIGTERM 后 writer 清理/订阅清理证明生命周期；合成 worker 合理，身份可复用真实主 token 以减少 override。 |
| test_tasks_auth.py | 重写 fixture | 使用真实用户登录；任务通过公开 submit 建立运行/成功/失败终态，取消门控任务并等 terminal；保留 unauthorized/CSRF 不产生副作用矩阵。 |
| test_tasks_router.py | 合并 | 与 tasks_auth 的列表无 result/详情有 result 重复，可并入真实提交完成后 HTTP 场景并保留大结果不在列表泄露的契约。 |
| test_websocket_console.py | 修改 | 真实账号和真实 socketpair 替代伪 fd/read loop/send mock，Docker SDK 是合理外部边界；保留处理 barrier、关闭顺序、错误脱敏和无效输入。 |

## DNS、事件

| 文件 | 决策 | 理由和动作 |
| --- | --- | --- |
| dns/test_api.py | 重写/合并 | 许多直接调用 router 并给 Mock User/config/manager；用实际 HTTP、真实账号、真实 DB/typed config、状态外部 adapter，检查受理≠完成、失败、只读观测及远端状态保全。 |
| dns/test_dns_manager_diff.py | 保留 | 真实 DB 输入+状态 adapter，known/unknown/empty 区分和禁止写入有效；fixture 从 test_reconciliation 移至 support/conftest。 |
| dns/test_dnspod.py | 收敛 | 外部 SDK mock 合理；保留实际 request model 序列化、域不存在、重试边界和 DNS 传播冲突；构造器赋值单测合并，sleep called 与受控传播门重复可删除前者。 |
| dns/test_huawei.py | 收敛 | 保留真实 SDK 请求模型、分页完整性/后页失败不能误删、过滤与空操作；减少 builder 链/default region 重复调用断言，prefer SDK 模型而非开放 MagicMock response。 |
| dns/test_manager.py | 重点合并 | _patch_active_servers mock DB、Mock config/旧状态 adapters 与 reconciliation 重叠；将规划输入边界保留为纯函数测试，业务初始化/配置变化/更新迁移到真实 DB+typed config 场景。 |
| dns/test_reconciliation.py | 保留并作为统一入口 | 持久服务器列表、状态 adapter、失败后新鲜重试、空期望不误删、取消 drain 有业务价值。用真实 Compose 读取替代 get_server_info fake；外部状态 adapter 仍合理。 |
| dns/test_record_replacement.py | 保留 | ConflictProvider 模拟真实 CNAME 冲突约束，验证先删除后创建和其他目标继续、失败恢复，属于独立业务模型，不是镜像差集算法。 |
| dns/test_router.py | 收敛 | 将 HTTP client 创建/发送构造成真实客户端+mock transport；保留错误/404 幂等/issued requests drain，差集矩阵可参数化并与 live 契约去重。 |
| dns/test_router_live.py | 保留/设施统一 | 真 mc-router 镜像、多次更新保持无关 route 与 no-op 零写入有效；接入 owned Docker helper，验证 label 后按 ID 删除，避免 inspect-name 到 rm-name 竞争。 |
| dns/test_utils.py | 保留/小合并 | diff 的固定输入输出是纯业务算法；删除 RecordKey 字段赋值/equality 本身测试，保持值/TTL/类型与 unrelated 保全边界。 |
| dns/helpers.py | 替换 | patch_accessor 自动调用 getter 并 patch resource，掩盖 dependency 类型；统一 typed fixture/config/stateful adapters，不再大范围替换业务 getter。 |
| events/test_bus.py | 保留 | 真实总线扇出、慢消费者淘汰和 reset 的业务约束。 |
| events/test_websocket.py | 重写 | 去掉 dummy_session/查询/subscribe mock；用真实聊天记录与总线发布，覆盖 replay/live 同 cursor 去重、无效/过旧 cursor reset、心跳、断线订阅清理。 |
| dns/__init__.py、events/__init__.py | 保留 | 仅包边界，无行为测试。 |

## 契约、架构、测试设施

| 文件 | 决策 | 理由和动作 |
| --- | --- | --- |
| contracts/test_api_contract.py | 保留 | 人工评审固定 wire schema/角色依赖快照是兼容合同；不能当运行时权限覆盖，禁止自动生成后无审查接受。 |
| contracts/test_cron_binding_contract.py | 合并 | 如 api-contract 已覆盖相同模型，把重复 property/required/default 逐字段精确枚举并入唯一 reviewed fixture；保留重要省略字段兼容性作为真实旧请求可读取用例。 |
| contracts/test_file_batch_requests.py | 合并 | 空路径禁止有业务含义，但只 model.validate 应并到文件 API 空操作拒绝且无副作用场景。 |
| contracts/test_release_upgrade.py | 保留/设施修改 | 固定 v5.3.0 SQL 独立于当前 metadata，升级两次、全历史/ID/API 是强覆盖；使用生产 Database wrapper 连接迁移后文件，避免手工 engine/session 配置漂移。 |
| contracts/fixtures/api-contract.json、api-contract.provenance.json | 保留 | 独立已评审兼容证据，治理不自动刷新。 |
| contracts/fixtures/releases/v5.3.0.sql、v5.3.0.json | 保留 | 发布版本真实 schema 合成业务数据及 digest，非可用生产凭据。 |
| architecture/test_import_boundaries.py | 保留 | 静态依赖约束为架构政策，不是业务测试替代；fault snippets 证明规则有效。 |
| testing/test_isolation.py | 保留/增强 | owned 资源、默认禁 Docker、破坏行为失败验证有效；添加外网隔离/loopback 允许、fixture 初始化失败资源回收，避免断言固定测试数量阻碍合理合并。 |
| fixtures/test_utils.py | 保留/扩展 | owned labels/随机名字/动态端口/按 ID 清理可靠；可泛化 mc-router owned 容器。 |
| fixtures/mc_client.py | 保留/收敛 | 真 Minecraft 协议客户端是测试驱动，不是后端实现副本；提供上下文管理和就绪/关闭期限，替代调用端 sleep。 |
| fixtures/__init__.py | 保留 | 包入口。 |
| support/runtime.py | 修改 | 资源 patch 生命周期统一但 Any/MagicMock 太宽松；DB 提供单入口，不鼓励独立 engine/session_factory 两路覆盖，外部资源优先 explicit typed adapter。 |
| support/environment.py | 增强 | 每测试路径和凭据隔离好；统一清除外部服务环境配置，默认网络 guard 防误连。 |
| support/tasks.py | 修改 | 等待真实终态方向正确；支持显式期望 cancelled/failed/completed、路径前缀、async client，统一 monotonic deadline；失败时输出 task 状态以诊断。 |
| support/mcmap.py | 修改 | fake binary 仅用于协议错误/取消/时序；正常能力用真 mcmap；临时脚本与 .args 归 tmp_path fixture teardown，config 用真实 typed 配置。 |
| support/regions.py | 保留 | 真实 region bytes 构造及独立解码验证数据保留，比调用被测 parser 充当 oracle 更可靠；不把简化文本 payload 误当完整真实 Minecraft NBT。 |
| support/restorations.py | 保留 | 历史兼容记录 builder 合理，固定 legacy 形态应自述来源。 |
| support/ownership_effects.py | 保留 | 隔离容器实际 uid/gid 副作用、数据字节和外部 sentinel 证明权限业务。 |
| support/api_contract.py | 保留 | 契约提取器；结果是兼容声明，不是业务 pass 证明。 |
| support/release_fixture.py | 保留 | 固定已发布 Git 代码生成历史库，避免当前 migration downgrade 自证。 |
| support/collection.py | 保留 | 完整 inventory/selection/phase 审计是发布策略，实现不需要为了 mock 治理重写。 |
| support/timing.py | 保留 | pytest 真报告记录及原子文件，失败也记录是合理证据。 |
| support/__init__.py | 保留 | 包入口。 |

## 每个迁移文件

专用真实 SQLite 文件是合理例外，不应强行使用已建最新 schema 的业务 db fixture。普通服务读取迁移后数据库可统一生产 Database wrapper。故障注入只用于失败原子性，不用 mock SQL 结果。

| 文件 | 决策 | 理由 |
| --- | --- | --- |
| migrations/helpers.py | 保留/标注边界 | schema_snapshot 和 Alembic 实际执行有价值；create_current_schema_downgraded_to 只适合结构等价，不是历史数据兼容独立证据。 |
| test_f2ee81a56fee_add_server_template_support.py | 修改 | 当前仅当前 metadata 降级后与 upgrade 比较；保留结构比对，补固定 legacy schema/数据或明确由 release fixture 承担升级数据覆盖。 |
| test_2026052400_add_restoration_table.py | 保留 | 实际升级/降级与启动 schema 验证；数据保留由专项和 release fixture 补足。 |
| test_2026060500_add_self_check_system_cron.py | 保留 | 真实 cron schema 与升级路径，不能以统一数据库为由改为直接 create_all。 |
| test_2026090700_preserve_chat_cursor_allocation.py | 保留 | 删除历史后新 cursor 不回退是流重放业务不变量。 |
| test_2026092400_unique_open_player_session.py | 保留 | 重复开放会话拒绝无修改、审查修复证据、陈旧报告、失败回滚都必要。 |
| test_2026092500_server_identity.py | 保留 | 生命周期 ID 不复用、歧义历史不能猜测，真实历史安全。 |
| test_2026092501_operation_journal.py | 保留/清理 | 恢复证据禁止破坏性降级；engine.dispose 应进入 finally 避免断言失败泄漏。 |
| test_2026092502_managed_schedule_binding.py | 保留 | 数据/执行历史保留、代际歧义、约束失败回滚，独立输入预期。 |
| test_2026092503_restoration_binding.py | 保留 | 恢复历史只绑定唯一生命周期，不猜测不可靠时间。 |
| test_2026093000_unified_restoration.py | 保留 | 升级不绑定同名新服务器、保留历史、防破坏降级、backfill 失败恢复。 |
| test_2026100100_task_results.py | 保留/清理 | 任务结果/操作历史保留，engine.dispose 置 finally。 |
| test_2026100600_snapshot_notes.py | 保留 | 注释字符限制/repository identity 是真实数据库约束。 |
| test_2026100700_name_based_restart_schedules.py | 保留 | 去绑定不修改计划历史、表替换原子性与失败重试。 |
| test_2026101800_task_failure_messages.py | 保留 | 安全错误升级/降级保留结果与恢复证据。 |
| test_revision_coverage.py | 修改定位 | 文件名存在≠行为覆盖；保留为清单完整性检查并明确不能证明 schema 或数据测试质量。无需扩张复杂静态规则。 |
| fixtures/duplicate-open-session-repair.json、fixtures/restoration-history.json | 保留 | 独立历史输入与期望业务证据。 |
| migrations/__init__.py | 保留 | 包入口。 |

## CI 文件

| 文件 | 决策 | 理由 |
| --- | --- | --- |
| ci/test_api_workflow.py | 保留 | 最小凭据分发、配置秘密不泄漏、清理失败继续其他资源是发布业务；单纯 YAML 精确 job 名仅限不可绕过 gate 约束。 |
| ci/test_backend_timing_report.py | 保留 | 真实执行证据→耗时报告，失败/错 SHA 不发布历史。 |
| ci/test_browser_sharding.py | 保留 | 分片完整性、共享资源原子性、缺失/重复证据拒绝是 CI 合同；不固化没有意义的具体桶顺序。 |
| ci/test_collection_contract.py | 保留 | 覆盖遗漏/重复、改能力/策略、失败 phase、真实 pytest 子进程验证；不是实现镜像，错误输入必须拒绝。 |
| ci/test_dns_cloud_helper.py | 保留 | 外部 SDK mock 合理，清理只删 owned 范围、后页失败不删部分 inventory、凭据隐私必要。 |
| ci/test_release_gates.py | 保留 | 真 OCI 字节完整性和 shell pipeline 退出码验证，禁止未通过发布，不能为缩减用例弱化。 |
| ci/test_timing_history.py | 保留 | 来源/时间/组件/profile 隔离与 digest 约束，GitHub 网络替换适当。 |
| ci/timing-weights.json | 保留/由审计产物更新 | 成本输入只影响调度，不用于跳过测试；测试合并后按 CI 真实报告恢复权重。 |

## 不能用简单指标验收

- mock 总量减少不代表业务覆盖增加；外部错误、关闭失败、并发门应允许受控替换。
- 新断言应能够被一个明确业务错误击穿，如忘记 commit、错误密码放行、跨服记录泄漏、任务 202 后失败、CNAME 部分 inventory 误删、消费者退出未清理。
- 删除旧测试需映射到保留场景，最好记录“旧行为断言→新业务场景”表；不需要一条旧用例对应一条新用例。
- 专用 migration DB、多 Runtime DB、真实进程/网络能力不是统一政策例外漏洞，应显式命名并保留。
