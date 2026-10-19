# 边界领域治理最终复核

本文件修订初始 `audit-boundaries.md` 的“建议动作”，应与初始逐文件清单一起阅读；以下为当前实现决策，不再把初始建议当未完成项。范围内所有初始“保留”项继续保留，其原因见初始清单。无生产代码/API/schema修改，无本地全量测试，无提交/CI操作。

## 已实施结果与旧覆盖去向

| 文件 | 最终处理与保留业务 |
| --- | --- |
| test_auth_session.py | 真实生产 DB 用户、Argon2、登录 Cookie、错误/未知账号、CSRF真实创建用户且独立会话验证、logout后拒绝、数据库角色变化即刻生效、删除后相同ID不复用旧会话；增加真实WebSocket验证码→数据库验证→一次性ticket登录及敏感值不泄漏。旧405探测和假账号查询全部移除。 |
| support/auth.py | 新增统一真实账号构造/登录 helper，函数内部 commit 后返回实际身份；不替换任何鉴权服务。 |
| test_tasks_auth.py | 公开submit创建真实成功/失败/门控运行任务；真实账号登录；取消后等待future终态并检查worker finally；拒绝访问/CSRF无任务变更；完成任务列表省略result、详情保留result。 |
| test_tasks_router.py | 删除。其唯一“列表省略结果、详情保留”合同合并进上述真实完成任务HTTP场景，不再直接调用router。 |
| events/test_websocket.py | 删除dummy session、假SQL结果和假subscribe。真实数据库Player/Server+PlayerService写聊天，真实总线，持久重放/断线重连/去重/无效游标/过载1013关闭/心跳/匿名拒绝/断线退订。 |
| test_log_monitor.py | fake aiofiles/exists/getsize/create_task 与纯参数转发测试被真实文件→真实PlayerService→独立SQL会话断言替换；覆盖Unicode聊天不重复、UUID/在线会话、截断、重复watch、停止/全部关闭、缺失文件停止。保留真实轮询same-mtime和受控watch事件删除重建边界。仅外部skin API替换。 |
| test_log_parser.py | 所有既有语法/伪造防护断言保留；配置fixture改公共真实runtime_config，移除MagicMock配置。 |
| test_create_server.py | 公共database统一；成功终态后新会话检查Server注册和真实Compose文本；新增真实loopback监听端口冲突→409、无文件/无注册。已有跨Compose端口矩阵保留稳定宿主端口观察替身，避免环境占用使各例互相干扰。 |
| test_populate_integration.py | 公共database统一，轮询使用monotonic。删除末尾两个假submit_durable测试；task_id已有真实流程，task_type/server_id/cancellable合同合并进真实7z终态流程。无行为覆盖被单纯删除。 |
| test_websocket_console.py | 用真实账号/密码建立Cookie，路径调整仅为子应用挂载测试。新增真实socketpair双向UTF-8字节、关闭FD/peer EOF，保留控制Docker错误和消息处理barrier的既有适配层故障测试。 |
| test_execution_observation.py | 公共runtime_config/database替代重复schema和fake mcmap配置。历史/保留预览元数据继续显式构造，因为被测行为正是读取没有活动worker的已有索引状态，不应强行生成昂贵新世界任务。 |
| test_adapter_error_logs.py | 端口扫描用真实Compose文件和manager；发现真实manager会先过滤无效文件，因此场景精确定义为“发现后Compose被替换”，只保留这个竞态控制门，真实读和解析/错误日志执行。mcmap错误JSON使用真实StreamReader+有限Process对象为协议故障注入，真mcmap成功路径不会自然产生坏JSON，不替换为随机故障真实二进制。 |
| test_compose_file.py | sync/async两套临时文件手工清理合并tmp_path参数化持久化往返，检查实际镜像/端口/environment字节值。其余转换器与完整Compose场景保留，分别验证短语法和输入类型组合。 |
| test_decompression.py | 中间进度从固定映射27改为受控进程实际输出25%对应消息+范围+未发布+终态字节。低层百分比类型例合并到实际提取文件内容；高层TaskProgress类型例合并到进度单调/终态/真实内容场景。zip/7z、深层路径、发布保全、清理失败和任务集成各有独立输入/输出，保留。 |
| test_process_resources.py | 保留真CPU进程、PID复用、AccessDenied、线程门；取消固定interval==1断言，线程门仍验证一次有界非阻塞采样和多核值不截断。 |
| dns/conftest.py、dns/fakes.py | 共享fixture由test模块迁出；真实生产DB、持久化typed DNS配置、真实Compose读取。fakes仅实现外部DNS/Router远端状态及故障/门控，不复制规划算法。 |
| dns/test_api.py | 全部改HTTP+真实用户+真实配置+真实任务+真实manager。验证只读pending计划、202受理未完成、423重复返回同任务ID、终态records/routes、失败保留其他目标进度且重试恢复、disabled/匿名/CSRF无副作用、外部读取安全错误。 |
| dns/test_manager.py | 删除mock SQL integration、重复不可读Compose、构造器链、hash长度/稳定性与初始化异常转发镜像。SQL/不可读/热配置行为由真实reconciliation/API覆盖；保留纯规划和并发读/配置刷新drain故障门。DNSPod/Huawei用typed配置+可用外部状态adapter检查初始化/读取/关闭。 |
| dns/test_manager.py（历史命名测试） | 旧fake返回server_info.name不同于目录，但真实MCInstance明确拒绝该状态。新例验证错名Compose→degraded且保留已发布连接、不创建legacy-name记录→修复Compose后按持久server_id恢复；没有放宽生产约束或删掉危险状态断言。 |
| dns/test_reconciliation.py | 使用共享真实DB/配置/Compose；unreadable用真实缺失Compose、恢复写入真实Compose，保留部分失败/空目标/取消drain及旧状态保护。 |
| dns/test_dns_manager_diff.py | 同样用公共fixture，不再import测试函数fixture；所有只读/unknown边界保留。 |
| dns/test_utils.py | 删除RecordKey字面赋值/相等性例。原API中的域过滤例合并到此文件，保留*.api、HTTP SRV、嵌套Minecraft SRV、www等无关记录与只读不变性。 |
| dns/test_dnspod.py | 删除仅assert sleep(2)的重复例；传播冲突门控仍验证删除已发出、创建尚未发出、完成后真实SDK请求模型字段和次数。SDK输入/输出规范化保留。 |
| dns/test_router_live.py | 保留真实Docker mc-router合同；清理改inspect完整资源验证label后按资源ID删除，关闭inspect-name/rm-name竞态。 |
| contracts/test_release_upgrade.py | 保留固定发布SQL/digest、两次迁移、全部历史和新ID/API独立证据；迁移后接生产Database并统一runtime数据库入口。 |
| migrations/test_2026092501_operation_journal.py、test_2026100100_task_results.py | 不改任何迁移断言；engine.dispose纳入finally，失败时同样释放真实连接池。 |

## 深读后明确保留（覆盖初始可能修改/合并建议）

- `test_compose.py`：不同游戏端口、版本、卷为空、缺字段/不合法容器名属于不同输入合同；不为削减数量机械合并。
- `test_async_fs_resolve_inside.py`：异常继承断言是公开可捕获异常合同，保留；路径/批量/链接测试无需数据库。
- `test_docker_ps.py`：精确CLI参数保证JSON且no-trunc，属于外部协议调用合同；与真实Docker生命周期互补，保留。
- `test_log_exception_decorator.py`：metadata与运行时logger归属和对象不被格式化是跨业务异常封装合同，保留；资源取消样例已有真实finally。
- `test_operation_errors.py`：自建manager中的每项任务均等到awaitable终态，没有悬挂writer；故障注入为受控异常来源，保留。
- `test_runtime.py`、`test_identity_runtime.py`：必须独立构造多个Runtime/数据库验证所有权隔离，已用生产Database；不强行统一成单runtime fixture，故障close spy以关闭顺序和资源副作用为业务。
- `test_login_code_logging.py`：有意替换传输错误/代码轮转时间，保留可重复故障回归；真实验证码登录已补入test_auth_session。
- `test_task_stream_shutdown.py`：真Uvicorn/HTTP/SIGTERM+合成worker，身份override只用于专注进程关闭边界，真实鉴权已由auth/tasks覆盖，不强行把每个故障进程场景重复登录。
- `dns/test_huawei.py`：SDK builder、region、请求模型、分页完整性直接决定第三方API身份/查询范围，属于合理外部合同，保留；不要求普通测试访问有凭据的云服务。
- `dns/test_router.py`：外部HTTP/SDK适配器的状态码、404幂等、route差集、并发请求drain是协议边界，mock其客户端仍合理；真实router服务已有独立Docker测试，保留这些有控故障。
- `dns/helpers.py`：仅余DNS配置/初始化/客户端读并发边界使用，运行时API和普通持久化业务不再依赖它；保留为局部legacy fixture，不宣称是全局首选。
- `contracts/test_cron_binding_contract.py`：核查固定api-contract不包含CronJobResponse和RestartScheduleResponse的完整schema，因此并非重复，保留确切optional/required默认值兼容性。
- `contracts/test_file_batch_requests.py`：空选择是Pydantic公开输入合同；此单例非常低成本且独立于其他API的权限/副作用，不为降低文件数量删除。
- `migrations/test_f2ee81a56fee_add_server_template_support.py`、`migrations/helpers.py`：metadata降级对比定位为结构一致性，不声称独立证明旧库业务；发布SQL固定fixture和其他revision数据断言已承担后者，因此保留。
- `migrations/test_revision_coverage.py`：仅要求revision文件级清单无遗漏，不声称测试数量证明业务正确；保留。
- `fixtures/mc_client.py`：是Minecraft外部协议客户端，非后端生产业务副本；调用端由主agent新增就绪等待和finally断开，无需为治理重写协议实现。
- `fixtures/test_utils.py`：已按ID/label管理资源；mc-router专用命令不强塞成Minecraft Compose fixture，专用所有权清理已修正。
- 其余初始保留的审计脱敏、事件总线、几何、监控解析器、日志轮转、启动迁移、revision迁移、发布契约、CI精确inventory/证据/发布gate均保留。它们使用独立固定输入/历史资源/真实子进程或明确外部错误边界，未发现需为本轮目标强行改写之处。

## 主agent接手范围与独立复核

主agent已实施 `test_config_binary_paths.py`、`test_audit.py`、`test_spa_fallback.py`、`test_monitoring.py`、`test_docker.py`，以及conftest、support/database/network/tasks/mcmap、testing基础设施。独立静态审查确认：真实PATH、HTTP请求体不耗尽及文件脱敏、SPA与静态/API404、监控去重复、跨会话提交/rollback、外网隔离与loopback、终态等待、临时二进制归属符合本轮目标。

已反馈两点由主agent处理：Docker SDK同步logs需off-loop/timeout，否则异步deadline不能中断阻塞；database_at应补初始化失败后连接释放的行为证据。不存在需要改动生产业务的阻断发现。

## 定向验证证据

- 第一批22例：auth_session（原11个当前登录/权限场景）、events websocket 8例、日志真实持久化和watch关闭2例、task owner流程1例，全部通过。
- 第二批6例中5例先通过：DNS受理/重复/终态、DNS失败恢复、缺失Compose保全、真实socketpair、真实7z populate。错名Compose用例揭露旧fake不可能状态，按上述真实恢复业务重写后通过。
- 后续4例：错名Compose恢复、DNS并发读取初始化、disabled API、固定发布数据库升级，全部通过。
- 新增码登录、async Compose往返、防伪造parser均通过；真实端口扫描因正常发现阶段已过滤坏文件而重定义为文件发现后替换竞态，修复后通过。
- 最后一批5例：端口竞态、解压实时进度、底层真实提取内容、高层终态及字节、真实配置提交/重置TTL，全部通过。
- 最新修改文件Ruff通过。此前16组修改文件定向Pyright为0错误；最后极小变更再由主agent全Pyright复核。
- Docker真实容器和未选择用例未在本地全范围运行；由最新SHA完整CI进行最终资格验证。此报告不宣称CI完成。
- 补充最后3个定向节点全部通过：真实创建任务终态后新会话注册/Compose内容、真实监听端口拒绝且无注册/文件、合并后的DNS域过滤不写入。已通过定向节点共42个，无累计全量。最后修改文件Ruff复核通过。

## Durable task 交叉复核补正

- `test_create_server.py`、`test_populate_integration.py`、`dns/test_api.py` 的 API fixture 现在在第一次获取 task manager 前绑定生产 `OperationJournal(database.session_factory)`。原先仅初始化真实表而没有启动完整 runtime，会让 `submit_durable` 静默退回瞬态路径；该遗漏已消除。
- 三条正向业务分别在新 SQL session 查询受理返回的 task ID 对应 `OperationJournalEntry`，独立断言期望业务 kind、`succeeded`、非空 ended_at、writers_stopped；populate 同时查创建与解压两条操作。保留实际文件内容、DNS远端状态、受理不等于完成、重复423等独立业务证据。
- `test_tasks_auth.py` 明确用真实 `submit` 执行可控瞬态 worker，目标为通用任务权限、CSRF、列表/详情载荷、取消清理、删除；它没有声称覆盖持久化业务。`test_decompression.py` 的 TaskManager 回归、`test_task_stream_shutdown.py` 的真实进程关闭亦属于瞬态 worker 生命周期合同。`test_runtime.py` 的 durable 路径已调用真实 runtime.start() 绑定 journal；`test_execution_observation.py` 已显式绑定真实 journal。鉴权、事件日志及纯 DNS reconcile 不创建 durable task，不强加无关 journal。
- 仅重跑三个已有正向节点：server creation、完整真实7z populate、DNS受理/重复/终态，均通过（3 passed）；三个文件 Ruff、定向 Pyright 均通过（0 errors）。这些是前述42个节点中的重复验证，未扩大成本为全量执行。
