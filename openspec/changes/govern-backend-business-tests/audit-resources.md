# 后端测试资源与执行域业务审计

审计范围：snapshots、world、files、archive、mcmap、ftb_claims、player_locations、background_tasks、operations、utils 的全部 Python 文件。只读静态审计，不运行测试、CI或修改代码。逐文件解析测试名、fixture、替换边界和断言；重点文件进一步阅读完整实现。未将静态审计视为通过验证。

## 判断准则

业务主干应从真实输入出发，经过实际服务/事务/进程，到独立读取的磁盘/数据库/任务结果。断言必须来自业务要求而非调用顺序或代码公式。纯算法的输入输出矩阵有价值，并非所有单元测试都过度。故障注入与时序门闩可保留，前提是不替代被测业务；未知 daemon 所有权、损坏外部协议、磁盘故障和精确取消无法靠每次访问真实外部服务稳定生成。真实子进程运行一个受控协议程序，只证明进程/协议契约，不等于真实 mcmap 业务成功。

默认统一 Runtime→生产 Database→新 Session；HTTP、worker、journal 共享 session factory，但每次工作独立 Session。取消/多连接竞争专门 fixture 必须保留独立 engine/connection，不能为了统一削弱锁与事务验证。完整配置对象上改叶节点，不使用缺字段 SimpleNamespace 代替配置。

## 优先处理

1. archive/test_archive_compression.py:305–372 假 submit_durable 关闭 generator，成功测试不会压缩；换真实任务、journal、7z，终态后解包比较内容，受理时不得声称完成。
2. files/test_file_operations.py:455 的 ownership 仅验证提交；改实际任务执行与所有权结果。mcmap/test_cache_ownership.py:48–122 的成功 mock 改真实 stat/owned Docker 权限。
3. player_locations/test_extract.py:96 的 AttributeError/replace 锁定 Python 方法细节，无公开业务承诺；归一化测试迁业务 owner，真实 NBT 提取补主线。
4. ftb_claims/player_locations 正常数据大多由 shell echo 的 JSON 构造，缺真实输入格式兼容主线；使用仓库已有 NBT/region helper 或小型公开结构 fixture 生成资料并调用真 mcmap。
5. snapshots/test_planner.py 和 world/test_restoration_model.py 中步骤元组/手工写状态再读的覆盖明显偏实现；通过既有真实恢复/回滚/历史链合并而非无据删除。
6. operations/conftest.py、world 的自建 DB 迁公共 fixture；保留 cancellation 的独立连接例外。mcmap/FTB/player 的 autouse 残缺配置移除。
7. 清理老 HTTP 成功链重复 fixture 和 401/422 宽断言，真实账户+注册服务器+真实 fd/Restic/7z；不删文件完整性、路径逃逸、代际、恢复失败边界。

## 不应误删

snapshots 新统一任务业务测试和 operations 的取消/恢复测试整体质量较高；真实 Restic/mcmap、文件和 SQLite 加可控门闩是合理组合。测试私有锁/监听器并不必然无效：用于泄漏检测的辅助证据可以保留，但应至少另有下一真实 writer 能成功、child 已退出、数据未改等结果证据。进度 100%、返回 task_id、调用一次都不能作为业务成功。

## 文件级处置

“保留”表示当前静态证据没有充分理由重写，不表示本次已运行通过；“合并”必须在保留的场景里明确覆盖原业务边界后执行。

| 文件 | 测试定义数 | 处置与业务理由 |
| --- | ---: | --- |
| `snapshots/__init__.py` | 0 | 保留：空包标识，无业务测试。 |
| `snapshots/conftest.py` | 0 | 修改：保留真实 Restic、SQLite、任务管理器；完整配置对象替换局部 SimpleNamespace；服务器使用真实 MCInstance 配合仅 Docker 状态适配替身；初始化后立即注册 finalizer，避免 yield 前失败漏清理。 |
| `snapshots/support.py` | 0 | 保留：集中真实任务终态等待、选择域 helper；不得把实现计算作为预期值。 |
| `snapshots/test_backup_progress.py` | 6 | 保留：受控真实子进程是故障/进度边界注入；保留真实 Restic 对照；删除单纯 lookup 调用次数时须保留结果身份断言。 |
| `snapshots/test_commands.py` | 16 | 保留：真实恢复、二次回滚、忽略、源缺失、受理竞争、历史持久化构成核心业务覆盖；门闩 patch 必须继续执行原函数。 |
| `snapshots/test_coverage.py` | 9 | 保留/参数化：路径覆盖与排除是业务选择规则；合并机械的单条用例，不删除祖先/兄弟/缺失边界。 |
| `snapshots/test_deletion_guards.py` | 3 | 保留：受理后删除保护、排空期间提交竞争；将 remove mock 辅助断言改为真实目录和新会话记录仍存在。 |
| `snapshots/test_empty_restore.py` | 7 | 保留：空快照不是无操作；删除范围、未选择兄弟、忽略项、外链安全及有限删除取消均有独立价值。 |
| `snapshots/test_execution_events.py` | 1 | 保留：数据库接受先于任务注册仍可观察；不能用任务 manager mock 替换。 |
| `snapshots/test_find_snapshots_covering.py` | 6 | 保留/合并：AND 覆盖、时间顺序、排除规则应保留；输入合法性与 scopes 相同情形可参数化集中。 |
| `snapshots/test_ignores.py` | 28 | 修改/合并：保留真实 server.properties 解析、级别名、别名安全；one-read/no-read 调用次数仅作明确 I/O 预算测试，其余并入业务结果矩阵。 |
| `snapshots/test_logical_exclusions.py` | 13 | 保留：逻辑别名与物理执行范围区别、重定向、历史保护是高价值反例。 |
| `snapshots/test_maintenance_tasks.py` | 4 | 保留：删除保留实际引用直到读者退出、cron 竞争，不以 202/进度替代终态。 |
| `snapshots/test_mixed_exclusions.py` | 6 | 保留：混合保护/允许选择与失败前无副作用；对所有保护项不得仅检查方法未调用。 |
| `snapshots/test_notes.py` | 6 | 保留：注释失败不撤销已创建备份，仓库身份/重建隔离及 Unicode 边界。 |
| `snapshots/test_observation_endpoints.py` | 3 | 保留：仓库离线仍从数据库观察，异常替身必要；配置、鉴权统一 fixture。 |
| `snapshots/test_planner.py` | 15 | 重构/合并：大量 DirStep/FileStep 精确元组与步骤顺序重写实现；把缺失目标、选择去重、混合目录和文件转换为真实 Restic 恢复/预览结果断言，与 empty_restore/service_integrated 对照。保留批量查询预算需明确性能契约。 |
| `snapshots/test_preview_endpoints.py` | 4 | 修改：保留 HTTP 权限/CSRF/元数据/分页及任务清理；正向地图瓦片优先真实 mcmap，受控程序只用于进度和故障；鉴权不替换 session 查询。 |
| `snapshots/test_previews.py` | 11 | 保留：真实差异、绑定新鲜度、受理后取消、有限清理及无安全快照副作用。404/409 集合断言需根据已确认资源状态收窄。 |
| `snapshots/test_repository_use.py` | 5 | 保留：引用释放与仓库排他行为；service 拒绝调用的 mock 断言应补真实仓库内容未变。 |
| `snapshots/test_restic_client_integrated.py` | 23 | 保留：真实二进制兼容、字节恢复、删除范围、dry run、流式进度，优先作为 adapter 主干。 |
| `snapshots/test_scopes.py` | 7 | 修改：统一 Database fixture；保留 scope 语义、代际、别名和负坐标。 |
| `snapshots/test_service_integrated.py` | 19 | 修改：真实 Restic 保留，MagicMock 配置换完整真实配置；与 commands 的重复单路径成功场景可合并，保留 source/current 排除并集和 staging 语义。 |
| `snapshots/test_snapshots_basic.py` | 12 | 合并：构造属性等于输入、Pydantic 属性透传删除或并入真实密码/无密码仓库；保留绝对路径、空目标、矛盾 includes/excludes 拒绝且无副作用。 |
| `snapshots/test_snapshots_endpoints.py` | 30 | 重构：1778 行包含重复密码/无密码、配置/mock manager、手工环境；共享真实服务器和数据库 fixture，选代表 HTTP→终态→文件完整性链；保留权限、路径范围、CSRF、排除语义；401/422 宽断言收窄。 |
| `snapshots/test_snapshots_nopassword_integrated.py` | 6 | 合并：与真实 Restic integrated 的核心场景参数化密码模式，不重复全部业务恢复矩阵；保留无密码初始化真实验证。 |
| `snapshots/test_target_rules.py` | 2 | 保留：逻辑规则、动态配置、认证与注册状态；仅禁止 repository I/O 的 spy 有明确无仓库依赖契约。 |
| `snapshots/test_time_restriction.py` | 2 | 保留：开放/关闭时间边界是业务规则；不合并掉跨日和相等时刻两侧。 |
| `snapshots/test_world_absence.py` | 2 | 保留：真实 mcmap/Restic，来源不存在与外部 MCC 块完整性关键。 |
| `snapshots/test_world_commands.py` | 4 | 保留：四种范围、未选择数据及多根维度；端到端业务主干。 |
| `snapshots/test_world_endpoints.py` | 4 | 保留：202/停服/维护/共享历史；统一数据库和认证 fixture。 |
| `snapshots/test_world_history.py` | 6 | 保留：legacy 读取、损坏 absence、代际变更、安全备份失败取消。 |
| `snapshots/test_world_logical_exclusions.py` | 7 | 保留：逻辑 world 保护与区块 MCC 一致性；其内部选择键断言可辅以真实文件完整性。 |
| `snapshots/test_world_previews.py` | 1 | 保留：预览不改线上、选择与瓦片对应，真实二进制优先。 |
| `snapshots/test_world_recovery_lifecycle.py` | 3 | 保留：中断、取消、恢复历史与缓存终结；门闩用于真实生命周期，非替代业务。 |
| `snapshots/test_world_rollback.py` | 4 | 保留：重复回滚、安全副本与后来编辑；确保独立磁盘读数。 |
| `world/__init__.py` | 0 | 保留：空包标识，无业务测试。 |
| `world/conftest.py` | 0 | 修改：完整实际动态配置对象上修改叶节点，移除 autouse 的不完整 SimpleNamespace 配置。 |
| `world/test_artifact_recovery.py` | 4 | 保留：真实目录、重启证据与扫描竞态，未知写者不清理。 |
| `world/test_chunk_execution_boundaries.py` | 2 | 保留：真实进程模拟协议故障、结果与退出码一致、取消回收，这是可接受受控二进制。 |
| `world/test_chunk_prune.py` | 10 | 修改/合并：保留 preview→apply 资格、最新预览和匹配状态、清理后解锁；seconds_to_ticks/稳定 id 等机械小测试并入场景；_validate_inputs 全替换仅保留于故障边界用例。 |
| `world/test_crash_recovery.py` | 2 | 修改：迁入公共数据库，取消替换 get_async_session；以真实 Runtime 重建验证 pending/running→interrupted，成功历史不变。 |
| `world/test_layout.py` | 20 | 保留：真实文件树+fd，Vanilla/Paper/modded/别名/深度边界有独立业务价值。 |
| `world/test_locks.py` | 7 | 保留/合并：异常释放、串行、跨服独立和部分获取回滚是核心；holder 属性往返可合并入实际争用。 |
| `world/test_logical_snapshot_protection.py` | 3 | 保留：同物理块不同逻辑名称及 MCC 保护，不能用路径常量替代。 |
| `world/test_maintenance.py` | 3 | 保留：在线文件与离线 world 的冲突边界；真实服务器目录/注册，Docker 启停可替身。 |
| `world/test_operation_races.py` | 5 | 修改：保留删服超时/请求写者/地图断线争用；移除 mark_server_removed/AsyncMock session，使用真实 DB 检查服务器仍存在。 |
| `world/test_png_invalidate.py` | 9 | 保留：真实 PNG 删除、负坐标、部分失败继续和外链防护。 |
| `world/test_preview_lifecycle.py` | 22 | 修改：保留 TTL、活跃读者、竞争创建、磁盘限制、未知写者；_sessions/_repository_use 精确内部结构改为公共读/引用释放/磁盘及删除可用性。 |
| `world/test_prune_validity.py` | 11 | 保留：真实 mcmap 的 stale preview、并发应用、actor 和取消；私有锁检查辅以真实后继写者。 |
| `world/test_region_manifest.py` | 1 | 重构：唯一用例替换 ThreadPoolExecutor 后精确断言 workers=2；改真实文件清单在多种配置下保持完整/排序、目录变化可见。如并行度为硬需求另立有意义资源上限验证。 |
| `world/test_restoration_identity.py` | 2 | 修改：统一数据库，保留同名替换代际拒绝和 legacy 不授权回滚。 |
| `world/test_restoration_model.py` | 4 | 合并：手动赋 terminal/status/source 然后读取是在测 ORM；把持久化/Unicode/负坐标 schema 兼容保留为一个契约场景，其余依靠 commands/world_history 真实写入。 |
| `world/test_safety_backup.py` | 2 | 保留：历史路径与外链拒绝，安全边界必须独立。 |
| `world/test_selection_resources.py` | 3 | 保留：别名实路径声明和中断缓存清理；验证后继实际写入阻塞/释放。 |
| `world/test_world_restore_endpoints.py` | 2 | 修改：使用注册真实 MCInstance、完整配置；布局/维度 label 的 HTTP 展示保留。 |
| `files/test_application_ownership.py` | 11 | 保留：跨资源范围、真实恢复/压缩、未知写者、删除/创建竞争是完整性主干；统一实例和数据库 fixture。 |
| `files/test_common_file_operations.py` | 22 | 修改/合并：真实 CRUD 保留代表不变量，重复 HTTP CRUD 可参数化；所有权成功链用真实 stat（特权容器已有 owned_ownership），仅错误注入使用 mock。 |
| `files/test_file_batches.py` | 9 | 保留：全批预检、混合失败、未执行 pending、取消终态与原文件完整性。 |
| `files/test_file_operations.py` | 22 | 修改：ownership 接口目前仅 assert_called_once 且未执行任务，改真实 task/journal/终态和可见权限；统一服务器 fixture；精确 auth 状态码。 |
| `files/test_file_search.py` | 11 | 保留：真实 fd 搜索大小/时间/范围；与 API 同样矩阵可拆分低层完整矩阵及 HTTP 代表集。 |
| `files/test_file_search_api.py` | 20 | 重构：大量重复 MagicMock instance，换真实临时服务器；保留 HTTP 校验/权限/组合过滤，用真实 fd 触发非法正则而非 _run_fd_command 替换。 |
| `files/test_multi_file_upload.py` | 17 | 保留/合并：真实字节、覆盖策略、子目录和失效会话保留；只读取 policy 赋值的测试并入冲突决策→上传结果。 |
| `files/test_multi_file_upload_api.py` | 11 | 重构：统一真实实例；从预检→策略→multipart→读回磁盘的业务链验证，保留 HTTP 验证边界，压缩重复构造。 |
| `files/test_owned_ownership.py` | 1 | 保留：真实 owned Docker 特权文件所有权，明确能力 marker 及 fixture 清理。 |
| `files/test_path_confinement.py` | 5 | 保留：真实内外链接、目录和重命名；安全回归不去重丢失调用入口。 |
| `files/test_path_conflict_handling.py` | 6 | 合并：与 multi_file_upload 的子目录冲突矩阵重叠，收敛数据驱动场景但保留根/嵌套和 per-file 决策。 |
| `files/test_upload_failure_boundaries.py` | 5 | 保留：分片故障、部分字节、继续下一文件、整体失败和凭据屏蔽；read/chown 故障注入合理。 |
| `archive/__init__.py` | 0 | 保留：空包标识，无业务测试。 |
| `archive/test_archive_compression.py` | 25 | 重构：API fixture 的假 submit_durable 直接 aclose generator，导致只验证 kwargs；改真实任务/journal/7z并解包验证内容。流式/取消受控进程保留；命名 sanitization 参数化；精确 auth 状态。 |
| `archive/test_archive_config_paths.py` | 4 | 保留：真实配置路径、TUS 上传/hash/publish、链接重定向及等待租约后二次验证。 |
| `archive/test_archive_operations.py` | 23 | 修改/合并：真实上传/偏移/覆盖/取消/CRUD 保留，统一 task 等待；与 config_paths 共享客户端和输入 builder；精确 auth。 |
| `archive/test_archive_sha256.py` | 8 | 保留：真实摘要、完整输入、错误摘要不发布、并发 no-overwrite 保留一份完整结果；精确 auth。 |
| `archive/test_archive_tasks.py` | 4 | 修改：三处正向 hash 用自写 hash generator，优先在真实读/进程边界 gate 原算法，只有取消故障保留受控替代；保留 input lifetime 和 publication association。 |
| `archive/test_multi_path_compression.py` | 10 | 保留：真实 7z 多选路径、空目录、符号链接、argv 批次、命名冲突与完整输出。 |
| `mcmap/__init__.py` | 0 | 保留：空包标识，无业务测试。 |
| `mcmap/conftest.py` | 0 | 修改：移除残缺 SimpleNamespace autouse，统一完整配置。 |
| `mcmap/test_cache.py` | 8 | 保留/参数化：真实 mtime/空 MCA/缺失和秒精度是缓存业务策略；cache_paths 简单拼接并入实际缓存命中链。 |
| `mcmap/test_cache_ownership.py` | 9 | 重构：chown mock 次数与调用参数镜像实现；普通路径真实 ensure_dir+stat，root 权限使用已有 owned Docker fixture 验证不同 uid 的新目录继承及原目录不变，错误仅 fault injection。 |
| `mcmap/test_map_initialize.py` | 2 | 修改：download-client 外部网络难访问允许替代下载边界；palette 用本地 fixture 和真实 mcmap；不要 mock discover/compose 作为正常流程。故障泄密注入保留。 |
| `mcmap/test_palette_hash.py` | 11 | 保留/参数化：mods 变化/迭代顺序/忽略非 jar、level.dat 发现是缓存失效真实业务，保留输入改变→重建判定。 |
| `mcmap/test_queue.py` | 7 | 修改：coalescing/batching/failure 的受控 renderer 合理但补真实 mcmap PNG 内容场景；常规成功不只伪造 event/path。 |
| `mcmap/test_queue_cancellation.py` | 4 | 保留：受控 renderer 精确竞态与引用计数有价值；与 writer_ownership 的真实进程取消互补，不删除任一边界。 |
| `mcmap/test_region_path_validation.py` | 6 | 保留/参数化：真实文件树约束及 traversal 边界。 |
| `mcmap/test_regions.py` | 6 | 保留/参数化：真实清单排序/非 mca/空文件/目录，避免单独再测所有属性。 |
| `mcmap/test_remove_chunks.py` | 3 | 修改/合并：成功 argv 断言转为真实 mcmap 删除选中区块、未选区块字节不变；错误 NDJSON/非零退出仍用受控进程；与 world_absence 等明确覆盖映射。 |
| `mcmap/test_replace_chunks.py` | 4 | 修改/合并：精确 argv 的成功镜像可由真实源→目标区块值替代；外部 MCC/空块/未选区块有独立断言；错误协议仍保留。 |
| `mcmap/test_runner.py` | 12 | 保留/收敛：受控进程用于流式、超长行、stderr 压力、坏协议和回收；正向参数拼装合并为真实二进制资料验证。 |
| `mcmap/test_task_progress.py` | 1 | 重构：自造阶段+断言精确 60 是投影公式镜像；在真实 initialization/task 执行中 gate 最后阶段，验证阶段可见、100%不提前成功和最终产物可用。 |
| `mcmap/test_writer_ownership.py` | 7 | 保留：真实 child、文件 lease、独立维度并发、取消门闩、代际与 artifact 保留。 |
| `ftb_claims/__init__.py` | 0 | 保留：空包标识，无业务测试。 |
| `ftb_claims/conftest.py` | 0 | 修改：完整动态配置 fixture。 |
| `ftb_claims/test_cluster.py` | 11 | 保留/收敛：四连通/对角分离/强加载子集/跨区块与负坐标是业务算法；具体内部 cluster id 拼接仅保留确认为外部稳定契约时，优先稳定唯一身份和输入重排不变。 |
| `ftb_claims/test_extract.py` | 7 | 修改：正常 claims 格式用真实 SNBT/NBT 文件+mcmap 得到团队/领地再分组；malformed/error 用受控二进制。所有临时脚本由 tmp_path 管理避免断言失败漏清理。 |
| `ftb_claims/test_runner.py` | 4 | 合并：world 参数原样传入的测试替换真实资源场景；大 JSON 解析/错误事件保留受控程序。 |
| `player_locations/__init__.py` | 0 | 保留：空包标识，无业务测试。 |
| `player_locations/conftest.py` | 0 | 修改：完整动态配置 fixture。 |
| `player_locations/test_extract.py` | 8 | 重构：真实 player NBT→mcmap→HTTP→位置/维度/跳过原因；uuid 归一化归 players identity；删除锁定非字符串 AttributeError/replace 的偶然实现测试，替换公开非法输入不写入场景。 |
| `player_locations/test_runner.py` | 2 | 合并：仅 shell 回显固定 JSON 和 argv 子串并无业务数据提取；真实 player NBT 场景承担成功覆盖，故障协议保留在 mcmap runner。 |
| `background_tasks/__init__.py` | 0 | 保留：空包标识，无业务测试。 |
| `background_tasks/test_background_task_manager.py` | 30 | 收敛：30 个隔离 manager 测试中 getter/属性赋值往返并入提交→观察→终态→取消/删除状态矩阵；保留真正并发、非可取消、结果保留、future 多观察者。真实业务任务无需 mock manager。 |
| `background_tasks/test_cancellation_cleanup.py` | 3 | 保留：真实 shell 子进程回收、环境隔离、关闭 generator 后发布终态。 |
| `background_tasks/test_management_tasks.py` | 12 | 保留：真实 SQLite、重启、代际、重复提交、移除排空；Docker 状态边界替身合理，DNS/端口禁用需标明独立外部依赖。 |
| `background_tasks/test_task_events.py` | 19 | 保留/收敛：有界缓冲、断线不取消、共享事件、完整结果预算和终态门闩是契约；编码 call_count 是明示缓存性能约束可单独保留，避免泛化为所有业务的内部断言。 |
| `operations/conftest.py` | 0 | 修改：默认从 Runtime Database/session_factory 获取 journal，取消重复 create_all/engine、匹配 autoflush=False；专门多连接竞争 fixture 保留显式配置入口。 |
| `operations/test_acceptance_cancellation.py` | 5 | 保留：真实 SQLite commit/close 门闩；接受收据与重复 ID 不侵犯别的操作，不能替换 journal。 |
| `operations/test_api.py` | 4 | 修改：鉴权使用真实用户/登录，恢复 probe 返回外部所有权状态可控替身合理；读取历史/CSRF 保留。 |
| `operations/test_changes.py` | 12 | 保留：commit 后通知、回滚不通知、epoch/分页/溢出重置及保留业务记录。 |
| `operations/test_configuration_finalization.py` | 4 | 保留：配置失败收尾前阻塞和 cache degraded 并发状态；统一 DB fixture。 |
| `operations/test_coordinator.py` | 5 | 保留：多资源原子性、覆盖 lease、不同路径并发、真实等待者证明释放。 |
| `operations/test_daemon_operations.py` | 6 | 保留：无法确认 Docker daemon 副作用的状态有必要 fake；使用真实 journal，补充已有 owned Docker 主线映射。 |
| `operations/test_execution.py` | 9 | 保留：真实线程/子进程、门闩先注册、queued 取消、迟取消保留成功及未知 writer。 |
| `operations/test_finalization.py` | 2 | 保留/合并：cleanup 异常与子取消不是无意义镜像；可并入 execution 的有限 cleanup 边界。 |
| `operations/test_journal.py` | 12 | 保留：真实跨 store 事务竞争、容量、不可变终态、恢复引用；独立 engine 仅多 store 用例保留。 |
| `operations/test_journal_cancellation.py` | 8 | 保留：独立数据库连接、aiosqlite 真实 worker 与 cursor/close 故障，是必须显式例外的 DB fixture；锁内部状态只做辅助。 |
| `operations/test_process_descendants.py` | 3 | 保留：真实进程树/管道、发现失败不猜测所有权、线程收敛；不要为去 mock 改成不确定睡眠。 |
| `operations/test_recovery.py` | 14 | 保留/修改：未知 writer/probe failure 必须受控；默认缓存恢复/同名代际/配置比较已真实，统一 fixture；正常 probe可用 owned process 增加证据。 |
| `operations/test_restoration_retention.py` | 3 | 保留：安全成功历史可过期、未解决恢复材料必须保留。 |
| `operations/test_single_writer.py` | 4 | 保留：真实内核锁、子进程退出释放、多安装并行及取消 acquisition。 |
| `operations/test_submission_cleanup.py` | 2 | 保留：manager 拒绝不留 queued journal、关闭失败保留原错误；生成器有意抛错是边界输入。 |
| `operations/test_target_revalidation_cancellation.py` | 5 | 保留：真实 SQLite读取/独立 writer 证明取消不泄锁，不能误统一为同一 Session。 |
| `operations/test_task_finalization.py` | 1 | 保留/合并：任务未来/可见状态必须等待 cleanup，可与 background_task cancellation 合并但保留成功和失败的 journal 断言。 |
| `operations/test_task_observation.py` | 6 | 保留：断线释放监听、journal cursor、历史未加载结果不冒充 null；私有 listener 数量是泄漏检测证据可辅以重新订阅正常工作。 |
| `operations/test_task_retention.py` | 9 | 保留：有限内存句柄、结果保留、事务回滚不删 live projection、并发一致读取、安全错误跨重启。 |
| `utils/test_exec_cleanup.py` | 1 | 保留：AnyIO level cancellation 下真实 subprocess 必须被回收。 |
| `utils/test_sse_cleanup.py` | 1 | 保留：断线 send 取消必须关闭真实 source generator。 |

## 验证设计及验收

- 恢复：源快照→修改线上→恢复→新 Session 历史与原始字节独立读回；未选中的兄弟文件、忽略项、外部 MCC 对、快照记录均不能被错误改变。再编辑后重复回滚验证真实安全副本。
- 文件/归档：上传原始 bytes 并独立 hashlib 计算预期，真实发布后读取或解包；覆盖冲突/取消/失败保留输入生命周期，不能只测返回路径和 fake digest。
- 地图/提取：用真实 NBT/SNBT/MCA fixture；预期记录手写业务事实，不调用生产转换函数生成预期；正常输出经真实 binary，坏协议由受控 subprocess。
- 任务：使用 Event 门闩在真实业务边界暂停，验证受理不是完成、重复提交不会二次执行、断线不取消、取消后 child/lease/artifact 和 journal 全部终结。失败的预期覆盖部分写入与真实恢复保护。
- 测试删改映射记录旧用例→保留的业务场景及独立断言，不以数量/覆盖率作为意义证明。可在精选核心场景做窄范围 fault/mutation 检验（例如跳过排除规则、提前发布终态、取消回收缺失应使测试失败），不运行累计全量本地测试。

参照：backend/AGENTS.md、backend/docs/testing.md、background-tasks.md、operations.md、snapshots.md、snapshot-restoration.md、world-restore.md、files.md、server-map.md、ftb-claims.md、player-locations.md；openspec 的 snapshot-recovery、operation-consistency、operation-recovery、non-snapshot-background-operations、background-task-progress 契约。数据库/资源 fixtures 一致性治理不应改变产品可观察行为；如发现业务缺陷需独立说明并配套 API E2E 与覆盖目录。
