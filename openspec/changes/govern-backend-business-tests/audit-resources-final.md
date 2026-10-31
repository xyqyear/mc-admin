# 资源与执行域测试治理最终审计

逐项对应初始126个Python文件；文件减少是有明确业务承接后的结果，不是治理目标。生产代码未改。本报告记录实施完成的资源/fixture/断言变化及复审后有意保留的契约边界，不以静态审计或本地定向测试代替最终SHA完整CI。

## 实施及独立覆盖承接

- 正常SQLite都走Runtime生产Database；HTTP、服务、journal同factory且各自独立Session。迁移与真实取消/close异常/多连接锁测试保留专门engine参数。
- 残缺配置替换为完整ConfigProxy或实际配置更新；纯FTB/玩家提取无需DB。所有受控协议脚本归托管测试目录。
- archive API实际压缩、真FTB SNBT/玩家NBT、真mcmap remove/replace及palette增加业务主线。故障协议/竞态门闩/外部网络下载/未知Docker所有权保留明确替身。
- 删除Restic构造/模型透传、手工Restoration终态/回滚、成功argv和固定JSON、单纯manager getter；分别由真实仓库、commands历史/回滚、实际binary输入、真实任务生命周期承接。
- 原本已有的世界保护、源缺失、MCC、负坐标、缓存/资源清理、重启恢复、取消/断线等关键断言没有移除。

## 本agent定向验证

成功且不重跑的代表节点：journal重建持久化1、scope语义1、crash pending/running2；真SNBT与玩家NBT各1；真remove1、真replace两参数2、cache实际owner1及root跨UID权限适配1、region manifest两参数2、snapshot实际恢复/重复回滚1；压缩HTTP拒绝4和真实受理→终态→7z解包1；实际palette初始化1、map阶段到真实manager终态1。共21个不同参数实例。早期压缩fixture导入httpx/路径假设/journal未绑定失败已修复，最终正向和拒绝实例均已通过。没有运行任何目录/全量测试。

本域Ruff通过；限定路径Pyright一次通过。后续完整仓库静态检查由主agent负责。IDE diagnostics工具未提供。新无密码参数和最后fixture统一交完整CI，不为广泛累计本地测试破坏项目约束。

## Persistence域交叉复核

- 玩家fixture已消除HTTP/服务复用同一Session；服务提交后refresh/独立查询可观察真实持久状态。动态配置重载、模板HTTP与Runtime共用factory、自检真正执行后才写终态、服务器移除只结束目标玩家会话均有独立结果证据。
- manager factory通过ExitStack/finally在database销毁前shutdown；初始化异常也清理。没有发现新的Session关闭次序问题。
- 发现cron真实每秒触发与精确执行次数断言存在竞态，已交persistence agent改为真实APScheduler单次DateTrigger，同时保留持久cron配置重启语义；其反馈两个受影响代表节点通过。
- 发现templates migration及servers template creation API fixture缺少journal绑定，create_api_app不执行Runtime lifespan导致manager走内存模式。已交persistence agent补真实OperationJournal并增加独立持久终态观察；该项由其最终实施/验证报告确认。

## 文件级最终结论

| 原文件 | 当前测试定义数 | 完成处置/有意保留理由 |
| --- | ---: | --- |
| `archive/__init__.py` | 0 | 保留：包标识。 |
| `archive/test_archive_compression.py` | 22 | 已重构：HTTP→实际durable manager/journal→真7z→解包字节/空目录/未选文件保持；在实际压缩前门闩验证受理不等于完成，完成后独立journal读回。拒绝输入/401不接受任务且不改文件。 |
| `archive/test_archive_config_paths.py` | 4 | 已实施：重复create_all迁公共database fixture，HTTP/业务/任务同一生产Database。原有真实资源/SQL、故障门闩、权限或恢复断言保留。 |
| `archive/test_archive_operations.py` | 23 | 复审保留：TUS偏移、覆盖、完成前/后取消和归档CRUD是独立HTTP契约；与config_paths的自定义目录/retarget重验证互补。 |
| `archive/test_archive_sha256.py` | 8 | 复审保留：真实摘要/并发发布完整性，少量旧兼容401/422集合未影响字节与生命周期业务证明；鉴权精确行为已有公共和新增压缩/文件API验证。 |
| `archive/test_archive_tasks.py` | 4 | 复审修正初查：hash_file wrappers实际调用original再加Event门闩，真实hash输入/摘要并未被自写算法替代，因此保留全部生命周期边界。 |
| `archive/test_multi_path_compression.py` | 10 | 保留：真实 7z 多选路径、空目录、符号链接、argv 批次、命名冲突与完整输出。 |
| `background_tasks/__init__.py` | 0 | 保留：包标识。 |
| `background_tasks/test_background_task_manager.py` | 25 | 已合并：getter、submitted future身份、task type透传、Unicode单独用例、固定sleep终态用例删除；Unicode与metadata并入真实运行/终态生命周期，未来终结由该链及cleanup专门用例覆盖。保留状态查询/不存在/并发/取消/多个观察者等独立结果契约。 |
| `background_tasks/test_cancellation_cleanup.py` | 3 | 保留：真实 shell 子进程回收、环境隔离、关闭 generator 后发布终态。 |
| `background_tasks/test_management_tasks.py` | 12 | 已实施：重复create_all迁公共database fixture，HTTP/业务/任务同一生产Database。原有真实资源/SQL、故障门闩、权限或恢复断言保留。 |
| `background_tasks/test_task_events.py` | 19 | 复审保留：编码次数对应明确共享缓存预算，具有性能contract；主要断言均是实时事件/有界payload/断线和终态，不能为去私有符号删泄漏证据。 |
| `files/test_application_ownership.py` | 11 | 已实施：公共DB、需要快照的测试选择实际配置叶节点；真实Restic/7z/范围竞争和未知writer安全性保留。 |
| `files/test_common_file_operations.py` | 22 | 复审保留：实际文件基础操作与HTTP边界分别承担下层字节效果和输入/鉴权；chown命令形状是外部进程适配合同，真实权限由owned Docker与API新链补足。 |
| `files/test_file_batches.py` | 9 | 保留：全批预检、混合失败、未执行 pending、取消终态与原文件完整性。 |
| `files/test_file_operations.py` | 22 | 已实施（主agent）：ownership API实际任务/journal/chown与终态文件结果，非假submit。 |
| `files/test_file_search.py` | 11 | 复审保留：真实fd完整过滤矩阵，HTTP代表链补联通与验证，不重复实现搜索。 |
| `files/test_file_search_api.py` | 20 | 已实施（主agent）：实际临时MCInstance与fd HTTP代表链，参数/权限/目录边界仍保留。 |
| `files/test_multi_file_upload.py` | 17 | 复审保留：预检后policy必须可供第二请求查询，session/policy状态本身是跨请求合同；实际写入结果、目录、expiry另有完整断言。 |
| `files/test_multi_file_upload_api.py` | 11 | 已实施（主agent）：实际目录实例、预检/选择覆盖策略/多文件上传/字节与冲突结果。 |
| `files/test_owned_ownership.py` | 1 | 保留：真实 owned Docker 特权文件所有权，明确能力 marker 及 fixture 清理。 |
| `files/test_path_confinement.py` | 5 | 保留：真实内外链接、目录和重命名；安全回归不去重丢失调用入口。 |
| `files/test_path_conflict_handling.py` | 6 | 复审保留：根/子目录/混合映射是曾有风险的相对路径身份边界，精简成一条会丢失父路径重名反例；没有重复执行上传算法。 |
| `files/test_upload_failure_boundaries.py` | 5 | 保留：分片故障、部分字节、继续下一文件、整体失败和凭据屏蔽；read/chown 故障注入合理。 |
| `ftb_claims/__init__.py` | 0 | 保留：包标识。 |
| `ftb_claims/conftest.py` | 已合并/删除 | 已删除：纯提取不需数据库及配置，不再覆写不完整动态配置。 |
| `ftb_claims/test_cluster.py` | 11 | 复审保留：手写四连通反例、对角、强加载子集、负/跨区域、稳定身份均是地图业务显示与选择合同，不是生产算法复写。 |
| `ftb_claims/test_extract.py` | 8 | 已加强：实际SNBT团队/领地→真mcmap→连通簇/负区域/强加载/未知维度；原始文件不变。故障和特殊协议数据保留受控程序，脚本迁入托管临时目录。 |
| `ftb_claims/test_runner.py` | 2 | 已合并：固定成功JSON及world argv透传并入真实SNBT主线；保留超长JSON与错误事件两个独立协议边界。 |
| `mcmap/__init__.py` | 0 | 保留：包标识。 |
| `mcmap/conftest.py` | 已合并/删除 | 已删除：残缺配置autouse；仅需要配置的regions/queue/writer fixture显式依赖runtime_config。 |
| `mcmap/test_cache.py` | 8 | 复审保留：秒精度mtime是已记录兼容契约，空MCA不能渲染是边界；路径映射防止不同维度缓存串用。 |
| `mcmap/test_cache_ownership.py` | 8 | 已合并：内部ensure-dir调用镜像改真目录+stat及已存在文件不变；交叉复核后保留明确root跨UID权限适配用例，模拟data的12345:23456而process为root，断言chown确实收到数据owner，防止同UID结果自然成立。真实跨UID效果由files/test_owned_ownership及support/ownership_effects.py直接调用ServerMapCache.ensure_dir承接：data=12345:23456、既有cache=34567:45678，新层级必须继承data owner。非root/权限失败注入保留；不新增未声明root能力或跳过。 |
| `mcmap/test_map_initialize.py` | 2 | 已重构：成功链仅下载外部API替身；实际客户端ZIP纹理→真mcmap→调色板RGBA和缓存文件。各泄密失败点保留受控adapter故障。 |
| `mcmap/test_palette_hash.py` | 11 | 复审保留：输入顺序/版本/mod文件集合影响缓存失效，实际文件构造配合输入输出构成业务不变量。 |
| `mcmap/test_queue.py` | 7 | 已实施：配置使用实际MCMapConfig经ConfigManager.update_config，包含动态更新；受控renderer用于精确批次合并/错误协议，可独立复现并发，不替代binary业务主线。 |
| `mcmap/test_queue_cancellation.py` | 4 | 已实施：实际持久配置；受控取消/引用计数门闩保留，与writer_ownership真实子进程互补。 |
| `mcmap/test_region_path_validation.py` | 6 | 复审保留：真实路径校验安全矩阵，参数化不会提升有效性。 |
| `mcmap/test_regions.py` | 6 | 已实施：显式真实runtime_config；实际文件清单覆盖保留。 |
| `mcmap/test_remove_chunks.py` | 3 | 已重构：成功argv/固定JSON换真mcmap删除，选中块消失、未选块内容保留；异常协议和空输入保留。 |
| `mcmap/test_replace_chunks.py` | 3 | 已重构：成功argv/固定JSON换真mcmap源/目标MCA，单/多选择、未选块和源文件完整性独立读回；非零退出/错误协议保留受控进程。 |
| `mcmap/test_runner.py` | 12 | 复审保留：CLI参数/NDJSON是外部协议合同；受控真进程用于长行/stderr/取消/退出码等稳定注入；新真chunks/提取/palette主线防双方mock自洽。 |
| `mcmap/test_task_progress.py` | 1 | 已重构：去精确60公式；真实TaskManager+阶段门闩验证done阶段尚不终结future/result，最后清理后返回真实终态。初始化流为该投影单测的受控输入，实际binary生产在map_initialize覆盖。 |
| `mcmap/test_writer_ownership.py` | 7 | 已实施：公共DB、完整配置叶节点；真实child进程、租约、代际和未知writer artifact不变。 |
| `operations/conftest.py` | 0 | 已实施：journal使用公共生产Database/session factory；不复用Session。专门cancel/多连接测试保留低timeout或CloseFailure Session例外。 |
| `operations/test_acceptance_cancellation.py` | 5 | 保留：真实 SQLite commit/close 门闩；接受收据与重复 ID 不侵犯别的操作，不能替换 journal。 |
| `operations/test_api.py` | 4 | 已实施：重复create_all迁公共database fixture，HTTP/业务/任务同一生产Database。原有真实资源/SQL、故障门闩、权限或恢复断言保留。 |
| `operations/test_changes.py` | 12 | 保留：commit 后通知、回滚不通知、epoch/分页/溢出重置及保留业务记录。 |
| `operations/test_configuration_finalization.py` | 4 | 已实施：重复create_all迁公共database fixture，HTTP/业务/任务同一生产Database。原有真实资源/SQL、故障门闩、权限或恢复断言保留。 |
| `operations/test_coordinator.py` | 5 | 保留：多资源原子性、覆盖 lease、不同路径并发、真实等待者证明释放。 |
| `operations/test_daemon_operations.py` | 6 | 已实施：公共Database及完整runtime_config；未知Docker daemon ownership需要可控假适配，真实SQL记录/受理/取消/恢复阻塞不替换。 |
| `operations/test_execution.py` | 9 | 保留：真实线程/子进程、门闩先注册、queued 取消、迟取消保留成功及未知 writer。 |
| `operations/test_finalization.py` | 2 | 复审保留：两个极小用例分别保障清理异常与子取消传播，和实际线程/进程取消测试职责不同。 |
| `operations/test_journal.py` | 12 | 保留：真实跨 store 事务竞争、容量、不可变终态、恢复引用；独立 engine 仅多 store 用例保留。 |
| `operations/test_journal_cancellation.py` | 8 | 保留：独立数据库连接、aiosqlite 真实 worker 与 cursor/close 故障，是必须显式例外的 DB fixture；锁内部状态只做辅助。 |
| `operations/test_process_descendants.py` | 3 | 保留：真实进程树/管道、发现失败不猜测所有权、线程收敛；不要为去 mock 改成不确定睡眠。 |
| `operations/test_recovery.py` | 14 | 复审保留：未知writer/probe failure是必须受控的恢复输入；默认RecoveryService案例已不替换probe，实际SQL/目录验证缓存清理、同名代际和配置比较。真实进程登记/停止另由operations/test_execution与test_process_descendants覆盖，恢复用例专注持久恢复材料及阻止错误写入，未重复模拟进程算法。 |
| `operations/test_restoration_retention.py` | 3 | 保留：安全成功历史可过期、未解决恢复材料必须保留。 |
| `operations/test_single_writer.py` | 4 | 保留：真实内核锁、子进程退出释放、多安装并行及取消 acquisition。 |
| `operations/test_submission_cleanup.py` | 2 | 保留：manager 拒绝不留 queued journal、关闭失败保留原错误；生成器有意抛错是边界输入。 |
| `operations/test_target_revalidation_cancellation.py` | 5 | 保留：真实 SQLite读取/独立 writer 证明取消不泄锁，不能误统一为同一 Session。 |
| `operations/test_task_finalization.py` | 1 | 复审保留：成功/失败清理都必须先于终态，专门future语义比普通成功getter强，作为合并承接。 |
| `operations/test_task_observation.py` | 6 | 复审保留：断线释放监听、journal cursor、历史未加载结果不冒充null；test_operation_cursor_replays_commits_and_disconnect_unsubscribes已在断线后用terminal next_cursor重新订阅并验证无重复事件，私有listener计数仅补充泄漏检测；shutdown案例还验证stream实际StopAsyncIteration。 |
| `operations/test_task_retention.py` | 9 | 保留：有限内存句柄、结果保留、事务回滚不删 live projection、并发一致读取、安全错误跨重启。 |
| `player_locations/__init__.py` | 0 | 保留：包标识。 |
| `player_locations/conftest.py` | 已合并/删除 | 已删除：纯提取不需数据库及配置，不再覆写不完整动态配置。 |
| `player_locations/test_extract.py` | 8 | 已加强：gzip现代/raw legacy NBT+坏文件→真mcmap→准确位置/维度/UUID/跳过原因，并验证输入不变；删除锁定AttributeError.replace的偶然实现测试，脚本受托管。UUID输入边界仍保留为公开身份约束。 |
| `player_locations/test_runner.py` | 已合并/删除 | 已删除合并：原文件仅两个成功JSON/argv子串测试，真实NBT主线实际经过runner.extract_players承接。另保留extract::test_extract_error_propagates和test_extract_rejects_malformed_mcmap_payload错误事件/缺字段拒绝；mcmap/test_runner::test_extraction_cancellation_reaps_live_process[extract_players]验证真实进程组、取消、stderr reader完成及/proc PID消失。 |
| `snapshots/__init__.py` | 0 | 保留：包标识。 |
| `snapshots/conftest.py` | 0 | 已实施：完整 runtime_config，公共生产 Database；Restic/任务初始化后 try/finally 保证失败也排空。Docker状态小型替身保留用于离线/运行业务条件，实际文件/仓库/SQL/任务未替换。 |
| `snapshots/support.py` | 0 | 保留：集中真实任务终态等待、选择域 helper；不得把实现计算作为预期值。 |
| `snapshots/test_backup_progress.py` | 6 | 复审保留：受控真实子进程证明summary不能盖过失败退出、回调失败/取消必须收敛writer；lookup未调用约束退出前不得查询尚未提交的snapshot，成功后同时断言summary对应的结果ID/bytes。真实Restic的create/restore/rollback进度门闩另验证文件字节与最终历史，调用断言只是次序补充。 |
| `snapshots/test_commands.py` | 16 | 保留：真实恢复、二次回滚、忽略、源缺失、受理竞争、历史持久化构成核心业务覆盖；门闩 patch 必须继续执行原函数。 |
| `snapshots/test_coverage.py` | 9 | 复审保留：每个祖先/兄弟/空路径/排除边界对应不同选择语义；纯输入输出矩阵廉价清晰，参数化只是形式调整，不为减少数量合并。 |
| `snapshots/test_deletion_guards.py` | 3 | 复审保留：受理后删除保护、排空期间提交竞争均已有真实目标字节不变断言；排空超时案例已用新Session验证Server仍ACTIVE、写入门禁释放。remove mock只辅助证明危险Docker删除未执行；其他案例独立验证后受理backup仍运行、删除终态失败且源文件保留，不以mock计数代替结果。 |
| `snapshots/test_empty_restore.py` | 7 | 已实施：真实完整配置叶节点，保留空源删除/保护/外链/取消真实文件断言。 |
| `snapshots/test_execution_events.py` | 1 | 保留：数据库接受先于任务注册仍可观察；不能用任务 manager mock 替换。 |
| `snapshots/test_find_snapshots_covering.py` | 6 | 复审保留：真实仓库的覆盖AND、排序、排除和参数拒绝与HTTP层职责不同，没有只测赋值的用例。 |
| `snapshots/test_ignores.py` | 28 | 复审保留：I/O读一次保证同批level-name解释一致，no-token不依赖坏properties；其余真实文件/路径业务矩阵不重写算法。 |
| `snapshots/test_logical_exclusions.py` | 13 | 保留：逻辑别名与物理执行范围区别、重定向、历史保护是高价值反例。 |
| `snapshots/test_maintenance_tasks.py` | 4 | 保留：删除保留实际引用直到读者退出、cron 竞争，不以 202/进度替代终态。 |
| `snapshots/test_mixed_exclusions.py` | 6 | 保留：混合保护/允许选择与失败前无副作用；对所有保护项不得仅检查方法未调用。 |
| `snapshots/test_notes.py` | 6 | 已实施：普通 notes 使用公共 Database，真实仓库身份与注释恢复测试保留。 |
| `snapshots/test_observation_endpoints.py` | 3 | 保留：仓库离线仍从数据库观察，异常替身必要；配置、鉴权统一 fixture。 |
| `snapshots/test_planner.py` | 6 | 已合并（主agent）：删除精确steps元组成功用例；本文件新增test_mixed_and_duplicate_selections_restore_only_allowed_bytes，真Restic证明混合目录+文件/重复选择/保护/预览无写入。service_integrated既有TestRestore/TestStage承接单/多/缺失/ignored，安全拒绝及单次目录探测预算保留。 |
| `snapshots/test_preview_endpoints.py` | 4 | 已实施：共享case完整配置替代私有mcmap配置覆盖；HTTP权限/CSRF/生命周期保留。受控瓦片进程用于时序，真实初始化与世界区块另有实际binary覆盖。 |
| `snapshots/test_previews.py` | 11 | 复审保留：404/409覆盖source不存在及其他过期/冲突不同输入，核心结果是未做safety快照且未写live；其他案例有真实字节和终态。 |
| `snapshots/test_repository_use.py` | 5 | 复审保留：mock破坏性调用不发生本身是repository维护安全边界；maintenance_tasks/commands用真仓库验证结果，二者互补。 |
| `snapshots/test_restic_client_integrated.py` | 23 | 已实施：统一binary能力声明，删除导入期探测。真实二进制的各命令适配契约保留。 |
| `snapshots/test_scopes.py` | 7 | 已实施：生产数据库 session factory；保留真实路径、代际、范围矩阵。 |
| `snapshots/test_service_integrated.py` | 19 | 已实施：完整实际配置叶节点patch，统一binary能力声明；既有真Restic TestRestore/TestStage覆盖单/多/缺失/ignored并承接planner旧steps成功测试，本文件未新增混合范围案例。 |
| `snapshots/test_snapshots_basic.py` | 7 | 已合并：删除构造属性/Pydantic透传；实际无密码仓库参数化覆盖 None/空串/空白串。安全输入拒绝保留；密码恢复由 restic_client_integrated 承接。 |
| `snapshots/test_snapshots_endpoints.py` | 30 | 已实施：公共DB、实际配置叶节点，移除残缺MagicMock配置、导入期subprocess探测，精确401；保留真实Restic HTTP任务与文件完整性。Fixture中的实例适配数据用于无Docker的文件功能，不替代恢复业务。 |
| `snapshots/test_snapshots_nopassword_integrated.py` | 6 | 已实施：统一binary能力声明，删除导入期手工探测。复审保留六类真实操作：无密码标志由各CLI方法独立组装，单测一次backup不能证明ls/forget/restore均可用。 |
| `snapshots/test_target_rules.py` | 2 | 保留：逻辑规则、动态配置、认证与注册状态；仅禁止 repository I/O 的 spy 有明确无仓库依赖契约。 |
| `snapshots/test_time_restriction.py` | 2 | 已实施：真实配置模型，时钟/定时任务时间作为受控输入；全边界矩阵保留。 |
| `snapshots/test_world_absence.py` | 2 | 保留：真实 mcmap/Restic，来源不存在与外部 MCC 块完整性关键。 |
| `snapshots/test_world_commands.py` | 4 | 保留：四种范围、未选择数据及多根维度；端到端业务主干。 |
| `snapshots/test_world_endpoints.py` | 4 | 保留：202/停服/维护/共享历史；统一数据库和认证 fixture。 |
| `snapshots/test_world_history.py` | 6 | 保留：legacy 读取、损坏 absence、代际变更、安全备份失败取消。 |
| `snapshots/test_world_logical_exclusions.py` | 7 | 已实施：完整共享配置，不覆写mcmap顶层对象；逻辑范围/实际MCC完整性保留。 |
| `snapshots/test_world_previews.py` | 1 | 已实施：完整共享配置；真实preview业务保留。 |
| `snapshots/test_world_recovery_lifecycle.py` | 3 | 保留：中断、取消、恢复历史与缓存终结；门闩用于真实生命周期，非替代业务。 |
| `snapshots/test_world_rollback.py` | 4 | 保留：重复回滚、安全副本与后来编辑；确保独立磁盘读数。 |
| `utils/test_exec_cleanup.py` | 1 | 保留：AnyIO level cancellation 下真实 subprocess 必须被回收。 |
| `utils/test_sse_cleanup.py` | 1 | 保留：断线 send 取消必须关闭真实 source generator。 |
| `world/__init__.py` | 0 | 保留：包标识。 |
| `world/conftest.py` | 0 | 已实施：运行时真实完整配置与显式触发开关；配置依赖的世界集成测试共享数据库。纯FTB/player提取不依赖此fixture。 |
| `world/test_artifact_recovery.py` | 4 | 已实施：重复create_all迁公共database fixture，HTTP/业务/任务同一生产Database。原有真实资源/SQL、故障门闩、权限或恢复断言保留。 |
| `world/test_chunk_execution_boundaries.py` | 2 | 保留：真实进程模拟协议故障、结果与退出码一致、取消回收，这是可接受受控二进制。 |
| `world/test_chunk_prune.py` | 10 | 复审保留：秒到tick是公开用户参数契约；稳定task id支撑preview/apply关联；验证失败、最新preview及匹配apply并非仅投影镜像；受控worker只用于清理次序。 |
| `world/test_crash_recovery.py` | 2 | 已实施：普通生产DB+真实get_async_session，不再替换查询入口；新Session验证pending/running中断且成功记录保留。 |
| `world/test_layout.py` | 20 | 保留：真实文件树+fd，Vanilla/Paper/modded/别名/深度边界有独立业务价值。 |
| `world/test_locks.py` | 7 | 复审保留：锁holder是用户维护反馈与冲突来源，正常/异常/跨服原子性均有行为价值，测试实现没有复写加锁算法。 |
| `world/test_logical_snapshot_protection.py` | 3 | 保留：同物理块不同逻辑名称及 MCC 保护，不能用路径常量替代。 |
| `world/test_maintenance.py` | 3 | 已实施：重复create_all迁公共database fixture，HTTP/业务/任务同一生产Database。原有真实资源/SQL、故障门闩、权限或恢复断言保留。 |
| `world/test_operation_races.py` | 5 | 已实施：重复create_all迁公共database fixture，HTTP/业务/任务同一生产Database。原有真实资源/SQL、故障门闩、权限或恢复断言保留。 |
| `world/test_png_invalidate.py` | 9 | 保留：真实 PNG 删除、负坐标、部分失败继续和外链防护。 |
| `world/test_preview_lifecycle.py` | 22 | 已实施：实际WorldRestoreConfig字段设置、公用Database。私有sessions/repository集合仅作泄漏辅助；真实磁盘删除、活跃reader延迟释放、后继repository维护获准构成独立结果证据，复审保留。 |
| `world/test_prune_validity.py` | 11 | 已实施：重复create_all迁公共database fixture，HTTP/业务/任务同一生产Database。原有真实资源/SQL、故障门闩、权限或恢复断言保留。 |
| `world/test_region_manifest.py` | 1 | 已重构：真线程池/文件、单与多worker下完整清单、排序、mtime、空文件/目录过滤和删除可见性；去FakePool参数镜像。 |
| `world/test_restoration_identity.py` | 2 | 已实施：公共DB，新Session；自建任务manager finally排空。代际/legacy拒绝保留。 |
| `world/test_restoration_model.py` | 2 | 已合并：删除手写终态/手写rollback后读回的ORM镜像；保留legacy selection负坐标/JSON兼容往返。真实终态和反复回滚由snapshots commands/world_history/world_rollback承接。 |
| `world/test_safety_backup.py` | 2 | 保留：历史路径与外链拒绝，安全边界必须独立。 |
| `world/test_selection_resources.py` | 3 | 保留：别名实路径声明和中断缓存清理；验证后继实际写入阻塞/释放。 |
| `world/test_world_restore_endpoints.py` | 2 | 保留：使用注册真实 MCInstance、完整配置；布局/维度 label 的 HTTP 展示保留。 |
