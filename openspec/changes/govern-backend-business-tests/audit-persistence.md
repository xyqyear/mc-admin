# Backend persistence/business audit

审查范围：`backend/tests/{players,cron,dynamic_config,templates,servers,self_check,configuration}` 全部 Python 文件。已读取每个测试文件的场景与断言（AST 只读提取）、全部 fixture/resource patch，并深读高风险场景；交叉核对 backend/docs/testing.md、players/cron/templates/configuration/servers.md 与 cron-scheduling、game-port-configuration、log-parser-configuration specs。未执行任何测试，未改仓库。审查结论是静态证据，不表示用例已通过。

## 宏观判断

这些业务域已有大量高价值真实 SQLite、文件、Restic 和 Docker 测试，不能把“低层方法测试”一概归为过度测试：会话唯一性、丢失连接、旧配置兼容、模板变量类型、路径边界、调度星期语义均是实际用户契约。主要问题是：同一 Runtime 多套数据库；服务测试复用单一 Session；模块级 cron manager/registry；把后台任务提交参数当作业务完成；用 sleep 推测执行完成；真实逻辑被高层 mock 挡住；“覆盖了所有字段”但没有验证重载/失败不变性。

建议统一标准：真实临时文件 SQLite + 生产 Database 配置；同一测试的 HTTP/service/worker 使用同一 factory，每次获取独立 Session；独立 Session 读取已提交结果；外部不可访问的 Docker daemon/Mojang/DNS HTTP 可替代，文件/SQL/配置渲染/内部业务服务应真实；少量故障注入保留且断言副作用/无副作用；任务测试必须等终态与清理。

## 可直接实施的优先问题

1. `players/test_player_manager.py:73`、`test_chat_tracker.py` 的 factory 反复返回同一 Session，掩盖 missing commit 与事务隔离。所有 player fixtures 收敛到 Runtime DB，皮肤只替换外部 fetch，不替换 `update_player_skin`；异步皮肤任务 teardown 先 drain 后 DB close。
2. `cron/test_cron_api.py:24`、`test_cron_next_run_time.py` 手工替换模块函数和导入模块级 `test_cron_manager`；yield 前失败不恢复。`test_cron_manager.py:40` 创建模块级 manager；`test_cronjobs.py:10` 可变 registry 被多个测试注册新 job。改 function-owned registry/manager，使用 finally/ExitStack，注册失败也关闭 scheduler。
3. `templates/test_{template_api,default_variables_api,migration_api}.py` 三套 engine，只覆盖 `get_db`。migration 再 patch application.get_async_session；servers 的 create/sync/template-config 也多重替换。统一 Runtime DB 后删除入口补丁，HTTP 用独立 app 绑定本次 Runtime，客户端 context 关闭。
4. `templates/test_migration_api.py:573` 和 `:825` 用假 submit_durable 返回 task-123，直接关闭 generator，并自己重算 SHA256 来验证提交细节。这是明显的实现镜像。应走真实 task manager，检查受理时未完成、等实际终态后 Compose 和 source metadata、task history 一致；Docker 命令可替代。
5. `cron/test_cron_basic.py:245/:267`、persistence `:180/:268` sleep 2/3 秒后 `>=1`，甚至接受任意 ExecutionStatus；应等待业务 marker/终态，暂停后核对同一 execution id、计数和历史重载。test_cron_basic.py:96 已有事件屏障 + 真实文件副作用范例，可复用模式。
6. `self_check/test_events.py:30` 捕获 coroutine 随即 close，只证明 spawn 被调一次。应配置真实 Runtime self-check runner、触发事件、等待 owned task drain、核对 trigger/user/run/finding 持久化；禁用/不可用时断言无新 run。
7. `self_check/test_task_progress.py` 假 service 直接产预设 event 再逐字段验证转发；可替换真实 runner + 两个受控检查，其中第二个用 Event 阻塞，观察中间进度与终态落库。
8. `servers/test_lifecycle.py`、`test_sync.py` 替换 close_open_sessions，使注销/删除无法证明玩家确实下线。统一 DB 后恢复真逻辑并 seed 在线会话，验证仅目标服务器关闭、时间/时长正确、非目标保持不变。
9. `dynamic_config/test_dynamic_config.py:57` 仅断言 schema hash 长 16、`:209` 检查 `_schemas` 是实现锁定。改“同 schema 稳定/字段变化迁移版本变化”，注册通过公开 schema/access 观察。schema 内容是前端表单契约，应保留。
10. 文档漂移：`backend/docs/servers.md` 仍声称 managed cron generation binding、同名重建不能继承；`backend/docs/cron.md` 与 `servers/test_restart_schedule_identity.py` 已要求逻辑名计划跟随当前实例。configuration.md 末尾也称 generation-bound restart。应改为计划按逻辑名解析、单次已受理执行捕获 generation，避免后续测试治理按旧文档削弱正确行为。

## 文件级矩阵

标记：保留=有清楚业务契约；改造=保留场景替换 fixture/断言；合并=同一业务不变量可参数化/整合，但必须保留边界。

### players

| 文件 | 判断与具体行动 |
|---|---|
| conftest.py | 改造：另建 SQLite 并给 PlayerService 独立 factory；改 Runtime DB。保留独立 Session、runtime close 先于 DB teardown。 |
| helpers.py | 删除重复 engine/session/tempfile helper 后保留 UUID data builder；MD5 派生测试 UUID 是造数据不是 mock。 |
| test_chat_tracker.py | 改造共享 Session/内存 DB。保留忽略名、未知用户、非 v4、成就重复、带头衔与最长名字归属；持久化读取用新 Session。 |
| test_identity_resolver.py | 保留：真实 usercache 文件，Mojang 边界替换合理；附加字段、非 v4 不外呼是业务。可用真实 manager 路径代替 FakeInstance。 |
| test_player_cleanup.py | 改 DB；保留关联删除、实时配置筛选、AUTOINCREMENT cursor 不复用。补 preview 后配置/候选变化再删除的当前集合验证。 |
| test_player_manager.py | 高优改造：同 Session 替身、skin 高层替换；upsert/create/name-change 可与 service 场景合并，未知服务器/忽略玩家/离线无 join 边界不可删。 |
| test_player_map_profile.py | 改内存 DB 与 factory；缓存优先/外部失败回退/非 v4/流 dedupe/安全错误和 drain 都保留。已测失败流 active_sessions==0，是好范例。 |
| test_player_query_no_sessions.py | 改公共 DB；空历史/null last_seen、混合在线离线必须保留，时间改固定 clock。 |
| test_player_server_filters.py | 改公共 DB；参数化每种 history 查询和 unknown server 过滤有业务价值，不合并掉。 |
| test_player_system_advanced_integration.py | 高优改造：独立文件 DB、MagicMock config、200ms fake API、启动后 sleep。真实 ConfigManager、事件屏障/显式单轮，保留心跳持续、crash clamp、false positive/negative、unhealthy 与恢复后 resync。 |
| test_player_system_integration.py | 改公共 DB 和无意义网络 delay；大量 join/leave 和低层重复可整合为“日志→持久化→查询”流程；跨服务器、同 UUID 改名、大小写身份区别、成就跨服不能丢。 |
| test_player_system_stability.py | 改公共 DB/remove fake delays；保留并发重复 join、重复 stop 和多服独立。massive player count 不等于性能测试，可明确批量完整性并加强身份集合；24h/zero duration 可并入时间参数化。 |
| test_playtime_calculation.py | 改公共 DB/固定 clock；保留 mixed ongoing/finished、zero sessions 与 crash before join clamp。 |
| test_service.py | 优先保留范例：真实日志/DB、独立连接、公共事件、owned skin handoff、失败 RCON 不改变 online、跨 Runtime 隔离。可去 `_file_pointers` 检查，改第二次读取不重复聊天。 |
| test_session_uniqueness.py | 保留真实文件 SQLite 与控制并发边界；可复用生产 Database + 专用 session subclass，不能改内存单连接或串行化。 |

### cron

| 文件 | 判断与具体行动 |
|---|---|
| conftest.py | 改 Runtime Database；fresh manager 生命周期保留，避免导入测试模块当 support。 |
| test_cronjobs.py | 搬到 support/factory，registry 每 fixture 新建，sample command 用事件/实际文件标记可观察副作用。 |
| test_cron_manager.py | 去模块级 test_cron_manager；自定义 TestCronManager 为 fixture 技术细节，construction/init/shutdown failure 安全测试仍有隔离价值，可移 testing/support 生命周期测试。 |
| test_cron_api.py | 高优 fresh app/registry/manager/DB；现有 CRUD/filters/status 冲突保留；create/delete/update 增重载一致性；auth `in [401,403,422]` 应明确未登录 401，不能接受 422。 |
| test_cron_basic.py | sleep/count 改 terminal signal；registry internals 与简单字段回声可合并到 API/persistence；保留真实 scheduler dispatch、运行中 pause 不取消正在执行任务。 |
| test_cron_next_run_time.py | fresh fixtures；参数化 active/paused/cancelled/resume；多个表达式仅 next>now 太弱，应固定日期验证下一真实时刻；auth 错误精确。 |
| test_cron_persistence.py | manager shutdown 放 finally；sleep→终态；持久化历史不可接受所有枚举值；重启前后 execution id/count/messages 一致；用 fire datetime 替代 trigger.fields[4] 内部索引。 |
| test_cron_scheduling.py | 保留合法/非法 expression 原子性；触发器 class/fields 断言可降为具体 calendar fire time；无效保存后数据库和 live trigger均不变。 |
| test_weekdays.py | 保留参数化 calendar 结果，这是 cron 公共契约；normalize 字符串表可与 calendar 表合并，但所有复杂 weekday 边界保留。 |
| test_restart_scheduler.py | minute/hour parser 私有穷举可参数化，核心保留“冲突避让/paused 仍占位/独立计划不被排除/跨日/all slots fallback”；用实际 CronManager + SQL 配置做主场景。 |
| test_system_cronjobs.py | 保留默认创建/保护/用户修改不覆盖/坏参数修复；fields 索引换 calendar 输出，fresh registry。 |
| test_registration_boundaries.py | 保留：注册失败可重试、old fingerprint 跳过、坏历史可读、startup paused、running/terminal持久化/idempotence；故障注入 scheduler 或 commit 合理。 |
| test_execution_outcomes.py | 保留 terminal outcome/history/count；与 backup-skips 无须机械重复，可统一运行入口但 retain global/server lock。 |
| test_backup_job.py | 参数构造仅逐字段回声可合并；必须保留 retention required、path without server forbidden、实际 symlink/traversal confinement。成功参数应驱动实际 Restic retention 结果。 |
| test_backup_resource_outcomes.py | 保留真实 Restic + SQLite +文件、全局备份与 lock skips；可加强 snapshot restore/export bytes，当前只验证原文件未变不能独立证明备份含正确 bytes。 |
| test_backup_skips_when_locked.py | 保留 server/global lock 的禁止外部副作用；可与 execution_outcomes 合并到真实 history 断言。 |
| test_backup_error_safety.py | 优先保留：真实 Restic、失败 HTTP、notification 脱敏、取消后 journal/history一致且无遗留进程；HTTP 替身合理。 |
| test_cron_error_safety.py | 保留 auth/public constraints/secret 防泄漏；抛错误注入内部 manager是专门边界测试，不能因 mock 内部就全删。 |

### dynamic_config

| 文件 | 判断与具体行动 |
|---|---|
| test_dynamic_config.py | 改 hash 长度与 `_schemas` 实现断言；缺省/obsolete/nested migration、typed access-before-init 保留。JSON Schema defaults 服务前端，应保留。 |
| test_dynamic_config_api.py | 改公共 DB + owner app；合并纯 response 字段回声，用 PUT→GET→new manager reload→RESET 场景，非法写后旧值不变；鉴权保留。 |
| test_dynamic_config_integration.py | 改公共 DB；真实迁移场景高价值；update/reset 增fresh manager加载而非只看当前缓存；减少单独 `_initialized`。 |
| test_dynamic_config_union_validation.py | 大部分在验证自定义 BaseConfigSchema union 自动 discriminator，不能当普通 Pydantic 测试删；保留 actual DNS provider roundtrip/非法 union；scalar/no-union 冒烟可合并。 |
| test_log_parser_validation.py | 保留真实规则生成事件与旧值保留；非法规则应补 DB 重载保持原值（现仅对象身份）。 |
| test_runtime_config.py | 保留双 Runtime 实际 DB 隔离 + 动态读取，优先作为 fixture迁移基线。 |
| test_snapshots_ignored_paths.py | 保留 legacy missing-field 与 path confinement；默认值重复断言可并入 migration 场景。 |

### templates

| 文件 | 判断与具体行动 |
|---|---|
| test_default_variables_api.py | 高优共用 DB；PUT 目前只 len==2，应 GET 精确内容 + 新manager/runtime读取；duplicate rejection 后原值不变。 |
| test_template_api.py | 统一 DB/app；保留游戏端口/变量错误不写；delete 204 后 GET 404；update 需新 GET 验证；list>=1 改确切集合。 |
| test_migration_api.py | 高优替换假 task submit +手算 fingerprint；真实 task/文件/SQL、终态与重启后 metadata；dict order/list order/no-rebuild 是业务保留。 |
| test_template_manager.py | 变量类型/range/bool-as-int/regex/default 与 JSON schema 是用户表单契约，不能统称过测；简单 extract/render 可参数化，配 API 拒绝保留旧模板。 |
| test_variable_extraction.py | 保留 roundtrip/多变量每行/类型转换/歧义与warnings/quoted；低层表可参数化，别以实现重复删除边界。 |
| test_yaml_utils.py | 22个极小例可表驱动合并；保留顺序/类型/invalid YAML 对 rebuild决策影响，主要业务连接已在 migration API。 |

### servers

| 文件 | 判断与具体行动 |
|---|---|
| test_bot_integration_routes.py | RCON 外部替换合理；输出、tellraw 转义/多行/selector权限、timeout保留；overview 应从真实 server/player DB读而非高层 query mock。 |
| test_creation_identity.py | 优先保留：真实目录/SQL、并发名称端口、adoption generation、取消必须等IO、cleanup failure不泄漏；故障注入是必要手段。 |
| test_game_port.py | 保留 forms/安全旗标/占位/legacy parse，参数化广度来自公开规格，非过度测试。 |
| test_lifecycle.py | 公共 DB；删除重复 patch_runtime_resource；真实 close_open_sessions/cron 不宜全替；rollback 场景检查 DB tombstone、文件残留和无残留任务；docstring“all fake”与现实不符。 |
| test_misc_router.py | fake DB/get_active_servers 可替真实 DB与文件；保留漂移跳过、empty、generation nullable。日志具体异常正文应警惕与错误安全契约一致。 |
| test_restart_schedule_identity.py | 优先保留完整契约：名字非ownership、逻辑名重建、并发创建、暂停/取消不执行、捕获引用重验、exact target取消；对 restart command 的 mock 应至少有一个真实command→Docker边界案例。 |
| test_server_creation_template.py | 统一 DB；确保所有成功202等真实终态并核对 Compose+template metadata；static template空values场景也要终态副作用。 |
| test_server_references.py | 保留所有真实路径/symlink/generation边界；alias属性逐个等式可简化，不减跨代与缓存陈旧保护。 |
| test_servers_crud.py | 公共 DB；基本get/map/empty可参数化/整合生命周期；数据库唯一约束、removed append-only、最新记录选择和跨代完整保留；新Session读取。 |
| test_sync.py | 公共 DB、真实玩家关闭；dry_run应同时检查DB与文件/DNS无变，empty mount safeguard/force保持；当前文档说concurrent409，正式合同为423，校正文档并补确切并发业务场景。 |
| test_template_config.py | 公共DB；保留 retained snapshot 与 source deletion、legacy不强制端口、metadata完成才terminal；关注 render-preview setup只看202，应等创建完成再读。 |

### self_check

| 文件 | 判断与具体行动 |
|---|---|
| test_backup_mod_scan.py | 保留真实 JAR，改名不漏检、插件目录、坏档案不误报、依赖不是模块本体。 |
| test_config.py | config toggles/legacy IDs/schema 是用户配置契约，保留；纯内建集合减法可由真实runner禁用行为补强。 |
| test_current_state_query.py | 公共DB；12种时序baseline/patch/disabled/empty/tie 是当前状态核心语义，保留全部，不能机械合并只剩最新行。读取用新Session。 |
| test_dns_logging.py | DNS 外部异常替身合理；保留结果诊断与日志secret边界、programming error 交 runner处理。 |
| test_events.py | 高优从“捕获并close coroutine”改真实owned task完成+DB；禁用/不可用无副作用。 |
| test_game_port.py | 真实properties保留；真实Compose文件与instance替换高层get_compose；status可替Docker边界；不可变/整改指引/逐服务器隔离保留。 |
| test_jar_metadata.py | 保留真实ZipFile输入，多种真实metadata格式/坏数据边界，不算重新实现解析器。 |
| test_permission_owner_scan.py | 已用真实fd与filesystem，保留。UID通过mock Path.stat? 需能力环境允许真实chown时优先；不要要求普通CI必须root。 |
| test_runner_persistence.py | 公共DB；synthetic check用于runner聚合/retention可接受；game-port纠正场景改真实server DB/compose；保留历史evidence与当前状态独立。 |
| test_runtime_service.py | 保留双Runtime真实SQL隔离、异常隔离与动态禁用；这是治理基准。 |
| test_task_progress.py | 高优真实runner+受控check Event观测进度，终态未到不能有final result，最后核对persistent run。 |

### configuration

| 文件 | 判断与具体行动 |
|---|---|
| conftest.py | Runtime DB已正确；重复 metadata.create_all可公共fixture；port-conflict高层替身优先换系统端口边界，Docker up/down/status可替身，明确teardown先tasks后DB。 |
| test_application.py | 优先保留完整durable phase/fs/cancel/source回滚语义；phase故障矩阵不是实现镜像，因为独立验证实际文件+source+recovery阻塞+清理。可以减少仅重复 record.phase 的装饰断言。 |
| test_owned_docker_rebuild.py | 必须保留真实Docker+inspect实际容器environment+新container id，不能以便宜mock替代。 |
| test_preparation.py | 保留accepted配置深不可变，直接针对用户提交后异步执行被篡改风险。 |
| test_versions.py | 保留HTTP preflight/worker stale/newgeneration/legacy last-write、真实SQL+文件；不用自己手算opaque version。 |

各目录空 `__init__.py` 无行为审计事项。

## 实施验收建议

- 对统一 fixture 自身增加很少但强的行为测试：HTTP写入→service fresh session可见；service写入→HTTP可见；两个factory session不同；fixture init失败后资源关闭；Runtime teardown先drain再DB；下一个测试无前一个数据。
- 对替换实现镜像的场景，不按“少了多少测试”验收，而按业务证据矩阵保留错误输入、权限、并发、故障、恢复、取消边界；优先把薄弱路径接到真实existing核心逻辑。
- 不跑负责目录全量。选择新fixture行为 + 迁移代表性files/nodes进行本地定向验证，全部覆盖交给主agent完整CI。
