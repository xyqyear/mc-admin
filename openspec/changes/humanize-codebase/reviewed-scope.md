# Reviewed implementation scope

Source: code-humanizer audit at a773bbe5e3f7787c180b115ac0c40ff61d1e675e; 15 discovery and independent review agents, converged through round 4. The maintainer approved implementation. Each scope below is the final reviewed proposal, including revisions; titles do not override it.

## RT-01: 删除确认无消费者的内部入口与别名

删除 get_runtime 及仅用于它的 Request import、get_database、OperationJournal.stage 和 operation_journal 字典写入。保留 journal 对象、恢复顺序及会话入口。只移除列出的内部符号，不延伸到 SnapshotService.stage 或数据库 operation_journal 表。

Validation:

- 保留 tests/test_runtime.py 应用绑定/生命周期和 architecture import checks；无需为删除的死入口添加调用测试。

## RT-02: 固定类型的惰性运行时归属，显式关闭当前资源

以 Runtime 的具体 typed lazy properties 和明确私有缓存字段替代字符串容器；可选资源使用独立未初始化标识区分未创建与已禁用 None。composition root 保留明确依赖和惰性构造，不引入 descriptor、通用容器或插件 registry。为 journal、recovery、upload sessions/locks、process cache 等固定状态给出具体类型，保留 session_factory/database_engine 的独立测试 override。关闭阶段读取当前已构造字段，显式调用真实 close/stop/shutdown；保留 AsyncExitStack 的固定阶段和失败继续执行，不在资源构造时捕获可被替换实例的回调。previews/prune 的 preserve_artifacts 和安全标志仍由写入证据决定。同步调整 accessors、recover_runtime 及 owning fixture，不改变 ContextVar 绑定和 detached operation 清除。

Validation:

- 保留 test_two_running_apps_own_database_configuration_auth_events_and_tasks、partial_startup、ordered repeated-cancellation shutdown、close_failure 和 unconfirmed_writers 三种证据节点。
- 增加关闭未访问资源不触发 factory；disabled None 不重复构造；临时 override 恢复未初始化状态；替换资源后关闭当前对象一次。
- 保留 test_detached_work_and_new_requests_do_not_inherit_parent_operation、real DB/JWT/config isolation；保持日志 handlers、requests/streams 和 subsystem workers 的 drain。

## RT-03: 任务 summary 统一字段，detail 只增加 result

将公共字段仅定义于现有 BackgroundTaskSummaryResponse，BackgroundTaskResponse 继承并增加 required nullable result。具体 from_task 使用 Pydantic model_validate(from_attributes=True)，返回类型跟随具体 cls；保持两个公开 schema 名、字段 aliases/defaults/required 与列表不加载 journal result。cancel_requested 不进入 DTO。不要先把 task.model_dump 含结果整体复制到 summary，也不要创建通用 DTO mapper。

Validation:

- 保留 test_task_list_omits_result_payload、tasks_auth 的认证/CSRF与详情断言。
- 核对两个 schema 名、required 字段、error_code 默认、result=None/非空和 cancel_requested 缺席；列表 spy 只证明不调用 detail/result loader，业务断言仍验证 wire shape。

## RT-04: 共用有限数据库工作的取消传播协议

把现 _complete_database_call 原样提为具体 finite DB completion helper（例如 db/owned_calls.py），journal read/write wrapper 与 revalidate_targets 复用。caller 的 pre-checkpoint 保留在 coroutine 创建之前；journal 锁等待保持可取消，helper 仅在已拿到写锁后运行。普通失败原样重抛；取消仍优先且以数据库/close error 为 cause；成功后继续 checkpoint。finalize 保持独立清理工具，不将该 helper 用于外部 filesystem/process 或长业务任务。

Validation:

- 保留 test_journal_cancellation.py 真实 file-backed reader/write/rollback/mutex/close failure/context 节点。
- 保留 test_target_revalidation_cancellation.py AnyIO/asyncio 两种取消、重复取消、close failure、already cancelled 和 stale generation 拒绝；test_finalization.py 不削弱。

## RT-05: 并发测试验证同时进入和每任务独立结果

替换原 concurrent 节点为三个独立 entered Event 加共同 release gate；以有限 timeout 等待全部 entered，再释放完成。断言三个 receipt IDs 唯一，各 awaitable.data 和 get_task(id).result 均匹配该请求的固定 payload，running 期间 future 未完成。finally 释放 gate 并 shutdown。不要增加同义第二节点，也不使用总耗时阈值证明并发。

Validation:

- 改造 test_multiple_concurrent_tasks；保留 unique IDs、future 多观察者、running→terminal、cancel/shutdown。
- 同RT-05，保留unique IDs/future/取消与shutdown。

## RT-06: 只合并重复搭建，保留 receipt、类型和中间进度契约

将 receipt 的 non-null/type 检查合入基本 submission/completion 节点，并强化 receipt.task_id 与 manager.get_task 的对应、pending/running/ended_at 观察。将 message-only 和 numerical-progress 组织为 gated 参数化场景，分别保留中间/末值及 None。将 None/0/50/150 终值归一场景参数化，保留无进度不补100。负数和150若保留原值契约，以 generator gate 暂停后读 -10/150 再完成，而不是只读终态。保留 task_type 参数化或移入元数据参数化并准确命名；不宣称验证 feature worker。删除每个旧节点前在报告列出新节点及独立断言，取消/清理/Unicode/result/future 场景保持。

Validation:

- 旧 receipt→增强 basic submission 节点；message updates→含 None/数值的 gated progress 节点。
- zero/partial/150→completion normalization 参数化；negative→gated raw intermediate；task_type 透传留在明确的 metadata 参数化。
- 保留 non-cancellable、empty generator、Unicode、last result、remove active/clear retains active 与共享 future；durable cleanup/terminal tests独立保留。
- 覆盖映射与RT-06相同；不能按预计净删行数决定删除。

## RT-07: 删除失实说明与机械叙述，保留语义说明

删除错误 Singleton 说明、submit 的机械参数清单和失效示例、test/class 重复名称的 docstrings、Alembic 模板死注释及明显重述下一行的注释。对带实际语义的说明逐条保留或缩成一行：active-only filter、finite cleanup/cancel propagation、standalone Alembic/offline用途、runtime owning binding、SSE已开始与路由顺序等。设计细节留于现行 docs，不做全模块无差别 strip。

Validation:

- 纯叙述删除不新增行为测试；保留现有语义/行为断言。与生产逻辑改动分开记录验证范围。

## RT-08: 共享登记与释放 lease 的具体生命周期

引入一个只接收已建立 ResourceLease 的私有 async contextmanager，负责 add、revalidate、yield、finally remove及Event swap/set。delete/acquire 在原许可/冲突逻辑通过后调用它；保留 acquire 的 admission 生命周期、WAIT/REJECT/SKIP、parent reuse 和 delete 的 permit/freeze/drain。不要创建policy策略类或把父lease放入新登记路径。

Validation:

- 保留 coordinator atomic categories、path overlap、parent forgery、delete freeze；保留 real cursor close-before-release。
- 确认或补一个真实等待者在 acquire body 失败后继续获 lease，以及删除scope释放后可用；不以内部Event次数为断言。

## RT-09: 共用状态纯投影和 terminal dismissal

定义一个具体 OperationState→TaskStatus 纯映射（显式覆盖非terminal和现有fallback），两路径复用；publish_result 的 TERMINAL_STATES gate保持。recovered message/cancellable/error 与 live terminal处理仍分别负责。clear_completed 先列出terminal IDs，再复用 remove_task，返回实际移除数；只dismiss内存，不删journal或结果payload，不改变exclusive key回调。

Validation:

- 保留 test_completed_result_survives_dismissal_and_restart(single/all)、tasks auth/details、remove/clear保留running。
- 保留 late_cancellation committed outcome；核对各 active/terminal state、failure_code、recovered cancellable=False 与消息。

## ST-01: 共用玩家所属的 UUID 语法规范化

把32hex语法规范化移到players拥有、只依赖标准库的轻量身份模块；identity_resolver、player_locations和players router直接使用同一函数。保持任意位置横线删除、大小写、长度、非字符串异常时机；is_online_uuid/normalize_online_uuid仍独立检查v4，地图位置仍接受离线UUID。移除旧位置模块重复实现并同步导出和直接消费者。

Validation:

- 保留player_locations/test_extract.py:75和players/test_identity_resolver.py的usercache优先、离线拒绝远端场景。
- 保留test_player_map_profile.py的缓存/去重/non-v4不请求。
- 补固定输入期望表覆盖混合大小写、任意横线、非hex/长度、非str原异常；期望不得拷贝算法。

## ST-02: 删除确认无消费者的内部入口

删除dimension_labels.py及其world导出、runner.parse_event_for_test及仅为它存在的import、system内存采样分支。将chunk_prune测试改为直接以aclosing消费execution.run_prune，再删除service._run_prune_task，保留异常/关闭时生成器清理。维度标签HTTP配置、前端翻译和实际CPU监控保持。按独立死代码pattern提交并更新组件地图。

Validation:

- 保留test_chunk_prune.py的结果/geometry/进度业务断言。
- 保留world/test_world_restore_endpoints.py的dimension-labels和frontend mapping。
- 不写仅验证名字不存在的测试；实施时定向调用路径测试与类型/lint。

## ST-03: 公共 typed chunk 操作取代跨类私有调用

取消ChunkMergeJob和统一循环方案。把已有replace_selected_chunks/remove_selected_chunks以及结果计数验证作为world所属的公共具体操作，或仅公开现有executor操作并写真实类型。_run_chunk_op使用AbstractAsyncContextManager[MCMapProcess]及实际TypeAdapter事件union/泛型；类型无法自然共享时保留两段短typed结果处理，不引入策略注册表。两个外层循环、选择规划、进度、stage/copy/empty-MCA和owned_by参数原样保留；跨类私有调用改公共调用。只对明确完全相同的纯构造片段再决定是否局部helper。

Validation:

- 保留snapshots/test_world_commands.py:32/57和test_world_previews.py:17的真实MCA/MCC/ignore/未选中数据。
- 保留world recovery/safety/selection resources、preview lifecycle及mcmap replace/remove协议测试。
- 补共享操作异常事件、无result、错误count/returncode、取消关闭；只在现有覆盖缺口处加。

## ST-04: 渲染队列声明真实双 cache 接口

在mcmap所属轻量types模块定义最小RenderCache Protocol，仅包含只读data_path/palette_json属性、mca_path/tiles_dir/png_path和async ensure_dir。队列接收该Protocol，两个现有实现结构满足它；删除ignore/cast。Protocol属性只读以兼容ServerMapCache.palette_json property。不要反向import world，也不要把PreviewRenderTarget身份/generation/retention并入cache。

Validation:

- 运行backend Pyright；不写Protocol镜像测试。
- 保留test_writer_ownership.py:240的真实generation/FILES/palette/retention/reaping断言和queue cancellation/coalescing测试。

## ST-05: 上传覆盖策略只解释一次

先在当前函数局部获取并收窄已验证policy，不增加全局配置或新session框架。只为per_file构建decision map；当实际目标存在时，以一个具体局部决策入口返回允许写、exists或no_decision：always允许，never拒绝，per_file按决定/缺失处理。目标不存在时不要求decision。保持路径预检、shallow session copy、一次性/可复用session消费位置、partial success、有限当前文件取消完成及相同原因字符串。安全错误修复另属ST-10。

Validation:

- 保留三policy bytes/results、subdirectory mapping、no-policy/expired、reusable和cancel lease测试。
- 补check后创建目标：always写、never保留exists、per_file无decision保留no_decision；不存在目标照常写。

## ST-06: 归档使用已有 canonical confinement helper

用async_fs.resolve_inside替代归档目录和文件目标的containment算法，保留局部PathOutsideBaseError→HTTP400及现有detail；candidate的path.lstrip和已解析目录逻辑保留。filename和目录类型独立验证，init检查和execution下的canonical revalidation均保留。先characterize符号链接根/父目录/最终目标逃逸，特别注意await resolve顺序，不以去重复为由删执行检查。

Validation:

- 保留resolve_inside各边界、archive_config_paths真实upload/hash/publish任务及archive_operations/tasks的并发409。
- 补最终目标symlink escape、父目录alias、init后parent retarget与执行拒绝，不写outside。

## ST-08: 仅替换高层 ownership mock 顺序 oracle

保留recursive command argv/result/failure translation和lease tests。先用已有@docker能力、明确owned临时容器/树，或正式接入并由CI执行的root能力，添加真实stat(uid,gid)业务测试：data root/已存在父级所有者不变，新建每层匹配data owner；recursive repair覆盖完整子树。不要默认root skip而在普通CI永远不执行。等这些场景运行证据成立后，把92/109的重复高层exact-order节点合并/替换；root/noop/no-data/PermissionError和confinement独立unit边界保留。

Validation:

- 保留低层chown argv、nonroot/no-data/OSError、ensure_dir存在性/幂等/confinement。
- 保留recursive command参数/失败翻译和writer lease。
- 新增owned真实uid/gid效果后才删除高层顺序断言。
- 保留map non-root/no-data/OSError、file recursive argv/failure、existence/idempotence/confinement、real lease等待。
- 增Docker能力UID/GID最终stat，新层/旧层/data/sentinel均固定业务预期；能力必须进入正常qualification清单。

## ST-09: Process 缓存需要独立生命周期方案

先添加owned短命进程的当前采样/退出/缓存characterization，并测量constructor成本；纠正warm baseline注释。把缓存必要性和PID复用处理作为单独监控行为/性能设计：对固定interval=1优先评估每次使用fresh Process并退役runtime process_cache；若保留缓存则显式identity/eviction并记录新语义及真实收益。不能仅把dict.get改lazy或setdefault、不能以is_running宣称避免构造。保持一秒采样窗口、to_thread、NoSuchProcess→0和多核可>100真实值；PID reuse精确模拟只用psutil边界fake验证，不靠不可控强制内核PID复用。

Validation:

- 新增live/exit owned进程结果、退出前后fresh-session/runtime隔离和缓存清理。
- PID身份变化的确定性边界测试+至少一个真实CPU采样；错误类型/时机保留。
- 保留监控集成smoke，不把输出强制clamp 100或采样改nonblocking。

## ST-10: 上传错误公开原文必须作为独立修复

作为files独立错误安全行为修复排期，和ST-05 policy清理分开。先characterize并逐catch保留当前状态映射：require_upload_session与全路径preflight在外层try前，原404/400原位保留；FileApplication外部admission/lease的423及合法structured detail保持；内层_write_file的Exception仍转该成员status=failed并继续下一成员；循环内执行期resolve_file_path/mkdir等Exception（包括已authored HTTPException）当前进入外层catch，仍返回HTTP500和string detail，不因public_error_message或新增except HTTPException而改成400/423。仅替换这些catch的公开文字和日志：unknown成员失败给固定中文safe reason，unknown外层失败给原500的中文安全string detail；明确authored安全消息可在原字符串字段中按existing helper规则表达，不直接公开adapter构造的HTTPException.detail，也不把adapter原文包装成PublicOperationError。用现有log_safe_error写静态安全context，去掉logger.exception与参数/异常值。保持原try范围、成员partial bytes、session shallow copy/消费位置、父目录失败终止整批、当前文件finalize完成和CancelledError传播；不改为原子批次，不新增错误策略框架。同步spec/docs/E2E coverage，先有逐状态/partial/cancel characterization，再验证合成secret不出public或log。

Validation:

- 保留既有conflict/overwrite/no_decision、相对路径key、结果reason字段、session过期/消费及whole-batch preflight零写契约；按现proposal补充逐catch状态characterization。
- 新增preflight完成后受控symlink retarget：执行期escape仍500安全string detail，outside零写；不能用单纯初始escape400代替。
- 对真实UploadFile read/write/ownership失败检查partial bytes与下一成员实际成功落地；父目录失败仍终止批次。
- 取消当前文件finalize尚未结算时验证冲突仍被拒绝，结算后传播CancelledError且后续成员未写；one-shot/reusable消费位置保持。
- 在HTTP结果和应用日志注入synthetic credential，保留已确认authored safe消息；扩展owned API E2E及coverage.md。上述是未来实施验收，没有宣称本轮运行。

## FE-01: 将二级 hooks 工厂迁移为具体命名 hooks

先完成实际调用路径的 characterization，再按 query 工厂、mutation 工厂分阶段迁移。将内部 useX 直接命名导出，每个具体 hook 自取 QueryClient；files hooks 显式接收同一 serverId，useLogin 自取 navigate。将文件/归档下载保留为各自具体 hook 内的普通命令，复用 useDownloadManager，不把下载状态复制到 mutation。保留 queryOptions、options 覆盖顺序、keys、enabled、retry/polling、toast、错误时机和 accepted/terminal 差异。删除 FE-02 已确认死 hooks 后再统计迁移数量。同步静态 imports/测试 mocks/组件文档；不用通用 mutation builder 或新 hooks registry。

Validation:

- 保留 overview/detail metrics 共享与 stopped/unknown 门控；files draft/partial cancellation/taskPresentation；backups pending/progress100/503/cancel 边界。
- 保留 tasks waiter 的 transient503→真实终态、permanent404、OperationObserver 跨页/重连/dedup。
- 新增或补齐迁移调用者的受理仍 pending、删除/创建等到终态再成功、serverId 变更、登录 me 缓存与导航行为。
- 必要 lint/typecheck/import boundaries/build；只选直接相关本地用例，完整验证遵循远端 qualification。

## FE-02: 删除已全仓确认无消费的手写导出

删除 simpleDownload、4 个 task-panel selectors、2 个 sidebar selectors、blockToRegion/regionToBlock、VariableType、ApiResponse、ConfigUpdateRequest、useActiveDownloadTasks、useLoginPreference、CheckConversionRequest、isValidRegex、MapLayerMode 和 2 个死内部 hooks，清理因此无用的 import。实施时再次搜索全仓并完成 typecheck/build/边界检查。保留 stores 字段、实际 actions、API transport 方法、generated identity DTO；不借本项清空有运行时职责的配置/验证接口。

Validation:

- 保留实际 task panel/sidebar/loginPreference UI 与 persistence 行为；无须为不存在的消费写 mock-called tests。
- 执行必要 lint/typecheck/import boundaries/build，并按变动选择既有 architecture case。

## FE-03: 统一玩家身份的 UUID 纯规范化函数

新增 players 内具体 identity/UUID helper 公共入口，迁移 queries、playerLocationDisplay 和 controller 的实际等价操作，显式登记 import boundary 入口。保留 normalizedUuidOf 的 fallback、formatUUID 展示、shortPlayerId 和非法 UUID 的 null 策略。用手列的 null/undefined/empty、hyphenated uppercase、invalid length/char 场景补足 shared identity characterization，不引入泛化 identity registry。

Validation:

- 保留 profile cache 双消费者/uppercase dedup/disabled-stream 更新。
- 补同一 UUID 在 world 在线集合和列表/图层中同一身份、无效 id fallback 的业务场景；expected 不从新 helper 生成。

## FE-04: 复用同一 Minecraft→Leaflet 坐标 helper

从 map/mapConfig 导入纯 blockToLatLng，迁移 overlay 和 pan 的等价表达式。保留调用方 cellSize/16/512 换算、ring 顺序/holes、负坐标和 Leaflet layer lifecycle。最多把坐标约定说明集中到 helper；不删非显然 holes 或跨维度同步说明。

Validation:

- 保留 world URL/跨维度 pan、claims/player/prune overlay、tile revision 行为。
- 必要时补负 block 坐标与 chunk/region 不同单位的手列期望，避免仅断言新 helper 被调用。

## FE-05: 区分 SSE 解析失败、handler 失败及玩家有限流终态

作为显式行为修复，分两个可审查步骤。A：把 JSON.parse 单独放入 SyntaxError 容错，保持 malformed JSON 当前跳过策略；解码后调用 onEvent，handler failure 走外层现有 ApiError/onError、停止后续派发、finally reader cancel/release。不加入 retry、业务 event_type 或 task 状态到通用 reader。B：在 players consumer 按实际 complete/error 跟踪有限流终态，未经终态的正常 EOF 记录中文可恢复错误，abort/unmount 不报错；对 profile 必需字段做具体 wire 校验，unknown event 维持明确的忽略策略。将已有 hook error 作为非阻塞资料失败提示连接到两个地图的玩家区域并提供明确重试；保留已缓存资料、位置/地图与 fallback label，不把资料流失败变成恢复/prune任务失败。若 B 的具体重试/文案还需决定，先交付 A 的独立契约，B 不冒充纯 transport 清理。TF-01 的 tests 全部并入本项且只计一次。

Validation:

- 保留5种HTTP status/detail、CSRF/normalized error、profile 双 Query cache 更新和 uppercase dedup。
- 新增实际 reader malformed JSON→继续、handler throw→一次 onError/无后续 complete/无 onClose、跨chunk事件、abort 和 reader cancel/release。
- 新增真实 players hook missing-profile、profile后缺complete EOF、complete成功、error终态、disabled/unmount abort；不得覆盖已有成功缓存。
- B 增加真实地图玩家区域可见中文错误/重试恢复且地图仍可用；不以 hook.error 单断言代替 UI。
- 完整保留status/detail和shared-cache tests。
- FE-05 reader protocol、player hook与可见UI的新增oracle；不把源函数模拟描述为已挂载UI。

## FE-06: 先修 Cron 值错误，再类型化局部编辑状态

先实施独立 TF-02 并建立受控交互 oracle。之后以具体 Mode/typed action/typed per-mode draft 取代 string/any 和重复 switch；可用带 mode 的状态对象或 reducer，但保留各模式历史草稿，不默认抹掉 inactive 状态。共用五字段 split 仅对已等价的 effect/preset 路径，保留现有识别优先级、非法输入/raw串、prop回读和 disabled 行为。不要在此重写 CronExpressionDisplay 的自然语言解析或更改 cron 语法。docs/cron-management 应描述最终结构而非历史。

Validation:

- 完整保留 preset 不提交，显式保存才提交。
- 新增/保留各模式specific/range/interval/list/raw切换后记忆、raw↔visual、prop变更、disabled、非法/未完成输入、optional seconds。
- TF-02 0/空串回归在重构后继续有效；weekday0/7/name/compound保持原表达式。

## FE-07: 复用地图页面的具体展示接线，保留业务组件寿命

分两步：先将已有共同 controller 返回值分为具体 map/claims/players（及server query）对象，两个下层 controller 保留各自选择/preview/apply/recovery职责；随后提取2个页面真正相同的 dimension selector、map初始化展示和玩家列表绑定组件。保留每页 MapHelp 内容、restore mode确认、ServerStopGuard、prune 全维度语义与 guard。各对象依赖和 memo 稳定性按现有行为保留；不强制泛型 slots/registry/全部页面模板。WorldRestoreSidebar 与 backup panel位置/key/keepMounted保持，不借共享布局统一prune与restore挂载规则。TeamClusterList只读策略先保留；popover选择功能不在本结构项中隐藏、改名或删除。

Validation:

- 保留 sidebar 延迟map状态/optional tabs/history dialog 稳定与回滚。
- 保留 URL view/dimension、mode确认、跨维度 pan、online unknown/filter/cache、map revision、MapInit task pending/failed。
- 补2页面共用展示的loading/error/empty与用户操作 characterization，期望按各页当前差异手列；保留 restore/prune真实browser业务场景。

## FE-08: 精简 Cron 参数表单 API，保留实际 renderer 策略

复用 shared/forms/rjsfTheme.tsx。把 SchemaForm 缩为 Cron 参数编辑器或保留窄 shared wrapper，只暴露实际需要的 schema/formData/onChange；AJV、onChange解包、hidden-submit children、liveValidate=onChange、showErrorList=false、schema caller key保持。删除未使用submit/loading/formKey配置与相应 import；先确认enter/嵌套form事件后才可在caller直接渲染。同样保留 schema-driven job扩展，不硬编码各job表单。console.log删除属于明确诊断输出清理，不能改变RJSF验证失败/submit处理时机。更新 cron-management 与引用它的相关文档。

Validation:

- 保留 preset 不提交外层form与显式创建/编辑。
- 补真实动态 schema 切换、不保留前job参数、输入类型/默认值/验证、Enter不会意外创建、最终HTTP params正确。
- 无需 props透传机械测试；必要typecheck/build。

## FE-09: 共享最小路径树构造，保留三种树的交互差异

TF-03先独立修复并建立真实UI policy oracle；TF-04补完整path fixture。然后提取 files 内具体 path-tree纯构造/keys遍历，leaf保留真实payload；显式由caller准备当前path分段/key policy，避免新增任意schema/策略registry。保留输入顺序、首node语义、目录结果与文件结果、相对upload路径、search leading slash 和 currentPath导航。共享只有确实等价的小展示/展开操作；不要为少量UI样板引入tree框架，保持3种行点击语义与search自动展开。核对唯一caller后把onCheck收窄为array，父级一起删旧shape分支。FE-10可先单独缩图标输入，树payload合并收益不重复计预算。

Validation:

- 保留 uploads 顺序/1000+1/zero byte/abort晚到/partial结果与政策。
- 新增树同名不同路径、nested目录、search目录结果、leading slash/currentPath导航、自动展开/手动收起/高亮保持。
- 手列expected节点/用户路径，不能复制新构造算法作oracle；TF03/04回归必须继续有效。

## FE-10: 缩小 FileIcon 输入，删除伪造 metadata 适配

将FileIcon.file设为Pick<FileItem,name|type>，原FileTable完整DTO仍结构兼容。直接按当前节点/真实leaf payload供name/type，删图标专用DTO和假时间/size。搜索row类型选择保留：真实directory leaf用原result.type；虚拟parent按hasChildren目录，不把node.isLeaf等同file。若取消每row find依赖FE09 payload迁移，作为后续等价优化，不能提前改变首match语义。

Validation:

- 保留file table/search/upload目录与文件的呈现；search leaf目录必须仍显示Folder。
- 无需复制整张扩展名switch做镜像test，必要typecheck和相关现有integration。

## DM-01: 统一 finding 存储解码，查询形状保持

保留一个具名 finding storage decoder，直接接收现有 ORM/SQL Row 两种明确输入（或局部最小结构类型），使用同一字段构造和json.loads。两条查询仍各自使用原SQL和排序/current-state补丁选择，先执行现有空行过滤。不得为了输入统一增加mapping复制层、反射探测或Python全量重建current state。

Validation:

- 保留 full baseline/patch/disabled/empty finding/tie-break与历史持久化。
- 在既有持久化场景读取同一finding的current与history，核对固定evidence/remediation/时间/身份字段，含空JSON默认与损坏JSON原异常。

## DM-02: 移除测试专用 Compose writer，迁移真实 Docker 效果覆盖

删除 MCInstance.update_compose_file，明确列为未用内部接口移除，修正文档。删除该接口独有的running RuntimeError测试，但把“修改MODE并让真实容器消费”的效果场景迁入一个声明docker能力的配置应用测试：Runtime.settings.server_path与owned资源root一致，DB注册Server generation，配置prepared values通过现durable rebuild入口，等待真实终态后inspect固定env。另保留原Docker create/up/chat/RCON生命周期测试。以现行配置application的running/stopped意图、source/version/资源契约为断言，不伪称保留旧adapter拒绝running语义。

Validation:

- 保留真实MODE inspect、configuration test_success_preserves_running_intent_and_matching_source、failures_at_durable_boundaries、versions、configuration_finalization。
- 新Docker效果场景必须声明能力、own容器/networks并cleanup；兼容Legacy compose不要求SERVER_PORT。API配置apply E2E继续保留。

## DM-03: 移除三个测试专用聚合入口

删除get_all_server_compose_paths/get_all_server_info/get_running_server_names及因此闲置的imports；保留get_all_instances/get_all_server_names/get_instance。Docker测试改读已持有实例的Compose路径、server_info和running状态；不重建同样聚合算法，也不再测试已移除聚合器独有的名称/label过滤。修正minecraft docs当前接口列表。

Validation:

- 保留真实create/running/info/RCON/player内容场景、server_references confinement、cron/snapshot discovery；无新增替代聚合API。

## DM-04: 删除两个无业务消费者的配置便利 API

删除ConfigMigrator.validate_config及其专属test_validate_config；删除ConfigManager.get_all_configs与未初始化节点中仅该调用的断言。保留crud.get_all_configs、迁移/default factories、get_config/get_all_schema_info和generic HTTP module registry。验证集中在真实update/migration入口，不能同步收窄legacy加载或改变error/detail。

Validation:

- 保留test_config_access_before_initialization中get_config断言，migration/integration、runtime_config、log_parser invalid update cache不变及generic config API。

## DM-06: 按固定清单删除监控便利 API，保留 wire 和真实 source checks

首批限定删除CGroupStats、inactive_memory、get_device_by_id、BlockIODevice/Stats.total_operations、NetworkInterface total_packets/errors/drops与NetworkStats的packet/error/drop/外部流量便利聚合及non_loopback。保留所有raw DTO字段与HTTP实际使用的total_read/write/rx/tx_bytes；total_memory/active_memory/BlockIO.total_bytes/device_id与get_interface_by_name可保留为有效监控测试辅助，本轮不为少量行数再重排全部测试。删除read_container_network_stats包装，MCInstance直接用read_network_stats。移除仅对应已删packet aggregate的断言，仍断言实际接口rx/tx_packets非负与loopback。添加固定literal多设备/接口parser样本后再考虑纯公式测试收敛。更新docs准确列出保留内容，禁止跨域total_bytes机械删除。

Validation:

- 保留真实Docker cgroup/proc/container-ID/CPU/not-running/source断言和wire指标。
- 固定独立memory/io/net样本断言raw字段及生产使用聚合；不得用生产算法计算expected。

## DM-07: 删除六个确认无消费者的旧别名和 exports

只删除列出的六个赋值及对应checks package imports/__all__ entries。保留concrete函数、service本地alias、CHECK_DEFINITIONS/ordering与现test concrete imports。其他_check_*符号即使邻近也不在本项删除范围；若发现另有零消费者需独立证据。

Validation:

- 保留backup_mod_scan、permission_owner_scan、runtime_service和architecture checks；不删除功能测试。

## DM-08: 移除任意名字 proxy，保留 typed owning view和generic manager

删除ConfigProxy.__getattr__，保留七个typed属性与constructor captured manager，不缓存各配置model。fabricated generic proxy访问测试移到manager.get_config，删除旧proxy专属AttributeError文本断言；保留typed property未初始化/refresh/跨runtime测试。generic注册、modules/schema/update/reset接口保持。明确标记内部surface移除，不改HTTP404/400或显式属性原异常。

Validation:

- 保留runtime_config真实数据库/cache与owner隔离；generic config API/schema、migration integration。
- 保留manager未知module ValueError及未初始化 RuntimeError；typed属性read仍维持原行为。

## DM-09: 路由复用现有 user_to_public，原 guard保留

password login/get users/create user在现有id-none guard/filter通过后使用user_to_public。保留OWNER/IntegrityError/duplicate username/HTTP detail及JWT与cookie生成顺序；不把DTO映射搬到router共享层，不改安全文案作为cleanup。

Validation:

- 保留password login cookies/CSRF、identity_runtime当前role/owner/JWT隔离。
- 管理员列表字段、OWNER拒绝、duplicate user及两个None-id错误detail要保持；若缺现定向断言则补入route现测试。

## DM-10: 真正触发 union guard，保留独立的项目边界

在现union文件重写正例为父model.model_validate的固定authored payload并验证model_dump值；保留optional None/值、primitive mixed、BaseConfigSchema+primitive、all-base discriminator及自定义backend、nested/list、多union字段的有效边界。可合并重复临时类和纯schema基础性断言，但不得用仅DNS union代替generic guard分支。将真实DNSManagerConfig的Huawei/DNSPod provider和Manual addresses payload roundtrip，以及HTTP schema discriminator作为产品UI契约增强到真实config场景；不要把Manual塞进dns字段。把class-definition节点准确命名并显式区分构造不失败、实例失败时机；保留或合并第三多字段invalid场景，让先遇valid字段仍拒绝后续invalid。list样例只证明当前允许payload/schema，不宣称guard递归强制discriminator。

Validation:

- optional/mixed/custom/list/multi字段各有固定payload值断言；missing discriminator实例失败与later invalid field保留。
- Huawei/DNSPod provider+Manual addresses实际module/http schema；generic config API现用fabricatedschema，并未覆盖真实DNS。
- 保留invalid authored save不会改DB/cache的现有log-parser/API场景。
- 真实DNS authored provider payload接受/roundtrip和API schema variants。
- primitive/mixed/optional两分支输入保持；missing discriminator实例拒绝。
- nested list/custom discriminator schema能力保留或有明确等效合并去向；invalid save保留DB/cache。

## CN-01: DNS 旧接口受控退役，保留现行 DTO

第一步删除真正无调用manager _update helpers和三backend DTO，保留HTTP DNSRecord/status以及frontend task-result DNSUpdateResponse。第二步在observe/pure diff/apply_diff中迁移旧tests的managed过滤、只读、unknown非empty、CNAME替换、empty保留、provider update/delete-add和batch drain业务断言；旧空目标Python异常作为退役接口明确删除，不转嫁给新status API。然后删除get_current_diff/_get_current_diff、DNSClient.update_records/get_records_diff及router _remove_all_routes/_add_routes，并更新DNS docs。保留list_relevant_records、低层override_routes({})清空表的当前契约及其它有消费者入口；不顺带删除SDK/provider多实现接口。

Validation:

- 保留reconciliation stateful unknown/empty/partial/disable lifecycle，状态API以及过滤/无副作用。
- 将router:168 slow write gate迁到实际apply_diff的add/remove phase，等待全部已发request完成后报失败。
- provider测试改direct diff+apply_diff仍验证真实SDK payload；保留CNAME conflict/SDK drain/retry/pagination。

## CN-02: 统一 planner record 类型时显式迁移字段顺序

让pure generate_dns_records直接返回现有AddRecordT，所有构造均用命名参数，删除planner DNSRecord。全库迁移import、位置constructor、tuple equality/index/unpack和fixtures，保留manager:242当前转换意义直至所有消费者完成，随后移除重建。manager直接调用pure generators且传当前捕获domain，测试直接测planner；将fallback-only测试改显式domain。HTTP DNSRecord含record_id仍保留。保留record输出顺序、SRV内容/TTL和Routes。

Validation:

- 固定具体wildcard/manual A/AAAA/CNAME/SRV输出，assert named fields及序列顺序，含不同type/value sentinel。
- 状态API record字段与stopped ACTIVE服务器participation；planner无外部写。

## CN-03: 删除无生产需求的排时查询和pattern参数

删除check_time_conflict，generate_restart_cron保留exclude_server_id并输出选中minute/hour+'* * *'，删除无caller pattern参数。paused/backups/restarts/exclude tests改验证find_next_available_restart_time及真实schedule_auto_restart保存结果；保留完整custom_cron API、5分钟步进、精确managed generation排除和全占满fallback。不扩大到重新实现cron解释器。

Validation:

- 保留managed排除、同名独立job占位、paused、全槽位fallback、跨小时/日、原起点取整。
- custom表达式create/update/resume和cron-scheduling.spec weekday测试保持。

## CN-04: 先收窄 decorator 能力，安全日志另立项

在CN-09安全日志修复完成后，单独收窄内部decorator API：仅保留async包装和固定None失败返回，删除无生产消费者的sync/non-None能力及其专属示例/测试。类型写为async callable结果包含None，保留成功值、原func调用/await范围内TypeError失败返回、CancelledError传播和CN-09建立的静态安全context。不恢复raw参数repr、动态prefix插值或异常值/完整traceback日志；签名绑定或格式化中在安全阶段已退役的逻辑不重新引入。仅在本项明确移除能力时调整对应行为测试，保留所有真实生产callback的成功/失败/关闭覆盖及安全日志断言。保持小async包装，不增error-policy registry、容器或万能translator。

Validation:

- 保留async success return、普通异常→None且后续事件可继续、CancelledError传播。
- 补async错误参数调用characterization；皮肤失败保留join/session/event。
- CN09另换raw-log断言为synthetic secret不可见，不为删测试改变resilience。
- CN-09阶段完整保留sync/custom default返回行为；仅在CN-04独立退役时删除其专属断言，保留async成功对象/tuple/string与普通失败None的业务覆盖。
- 错误参数TypeError仍在原func调用/await的catch内返回None；CancelledError及其他不应捕获BaseException继续传播。
- 保留logger获取发生在原func执行之前且获取失败不被函数错误catch吞掉；成功路径不重新执行动态prefix/参数格式化，安全context与synthetic secret不可见断言持续有效。

## CN-05: 只保留显式 cron 注册入口

把test_cronjobs、test_cron_basic动态job和test_restart_scheduler sample jobs全部改显式register_func注册，保持identifier/function/schema/defaults/is_system相同。删除register及示例/文档，保留registry、get_schema_class和unknown retained类型契约。组件doc以现状描述显式注册。

Validation:

- 保留system保护/defaults/schema、unknown type历史可读与failed registration、fixture startup/shutdown-failure隔离。

## CN-06: 删除确实未使用的供应商锁与操作映射

删除Huawei _lock/property及纯存在测试；删DNSPod ModifyRecordBatch request TypedDict、union/literal成员、mapping和fixture patch。保留SDKRequest/Response/HuaweiApiClient protocols、实际请求mapping、构造初始化字段、to_thread/finalize、close/retry/pagination和DNSPod删除后传播延时。

Validation:

- 保留Huawei in-place与DNSPod replace行为差异、CNAME顺序、request payload、分页失败不部分返回、retry/close/cancel drain。

## CN-07: DNS 写测试必须检查实际外部 payload

保留network/SDK mock，DNSPod优先使用真实request类，或只记录from_json_string原始JSON的薄fake；断言CreateRecordBatch的DomainIdList和完整RecordList，以及DeleteRecordBatch原始ID列表。Huawei读取真实request并验证zone_id、fqdn、type、records、TTL及remove IDs。多目标顺序允许并发，按业务身份比较payload集合；不要用生产payload生成算法计算expected。将capability常量测试合并之前先保留实际update/delete-add差异。

Validation:

- 每个provider add/remove exact外部payload，empty零请求。
- 保留Huawei update字段、DNSPod delete/add传播边界、SDK分页/重试/drain/cleanup。
- 仍需要同SHA真实Huawei资格证据，unit fake不替代cloud E2E。
- 沿CN-07 preserve/add完整外部request、IDs、TTL、empty和drain，真实Huawei资格不能被替代。

## CN-08: 实际 cron 调度测试等待持久终态

合并两个second-star smoke为一个真实scheduler dispatch场景：通过一次性可控命令gate获取execution ID和可观察动作，停止后续触发但不取消该execution，释放gate，再用独立fresh DB session有界等待同ID COMPLETED，验证ended_at/duration/messages/count恰一次及真实命令副作用。保留registration-boundaries running admission/idempotence、stale trigger、start interruption和shutdown。不要靠提高sleep/timeout掩盖缺失finalization；fixture在DB patches关闭前drain。

Validation:

- actual APScheduler dispatch与command业务effect，fresh-session同ID终态。
- 保留RUNNING先提交、执行计数幂等、queued stale/pause/update/startup/cancel/shutdown清理。
- 沿CN-08保持实际scheduler、same ID、fresh committed终态、count幂等和shutdown/cancel清理。

## CN-09: 独立修复 raw public/history/log 输出

按现有owner拆成独立错误安全行为修复提交，CN-09先于CN-04装饰器API收窄。logger保留现有同步和异步包装、default_return参数与成功结果：Exception仍返回已配置default_return（默认None），TypeError继续在原func调用/await的原catch范围内处理，CancelledError继续传播；仅将raw args/repr、动态prefix插值、异常值和完整traceback日志替换为静态安全context。同步/自定义fallback能力及其行为测试本提交保留，由CN-04后续独立评估删除；不要因安全日志断言失效删除这些业务断言。用局部import复用errors.log_safe_error，或仅移动现safe primitive到低依赖owner解决logger↔errors循环，不新增通用translator/registry。Console逐catch保留原error/info字段、resize容错、send timeout及断连关闭策略，未知adapter文字改中文安全消息，原exception logging改安全type/stack context；profile SSE保留event_type=error/message及短DB session、取消/gather fetch消费者。Cron validation在原位置保留400/string detail，对字段位置和已确认安全的约束诊断去input/ctx及动态validator raw值；create/update未知仍500，ValueError按实际来源仅公开authored安全领域message，并按原分类保留400/404/409，不将未知全部改500或全ValueError当safe。Kuma实际请求继续使用配置URL/status/up/down/msg/ping，持久history/log不记录完整push URL；HTTPError和普通Exception仍安全记录后return，不反向覆盖备份结果。快照创建成功后forget HTTP423仍context.skip→SKIPPED并通知up/skipped后return；forget其它HTTPException仍重抛原错误到外层、发送安全down消息、由manager保留FAILED，已建snapshot保留；forget普通Exception仍仅安全warning并继续COMPLETED/up。主backup失败仍发送安全down并原样重抛；在cron manager失败history和skip warning消息边界也按来源确认HTTPException安全性，避免public_error_message盲保留adapter detail；不通过改原错误类型/status来遮蔽文本。CancelledError继续传播而非warning/成功，runtime-owned skin和profile消费者、durable writer drain与状态时机不变，skin失败不撤销已commit join/session/event。同步spec/docs/API E2E coverage；旧已保存history不趁此迁移或删除。

Validation:

- 保留test_log_exception_decorator.py中的sync/async成功值、default_return=42/'fallback'/None/False/[]、错误参数TypeError原捕获范围；新增async及sync可达取消/不应捕获的BaseException边界，CancelledError继续传播。raw参数repr、动态prefix或异常值/traceback暴露断言仅按新安全日志契约更新，不能连业务返回断言一起删除。
- synthetic secrets分别置于decorator参数、adapter错误、Pydantic input/ctx/动态validator文本和Kuma URL，HTTP/WS/SSE/history/app log不出现secret；authored safe消息与已有structured字段仍可读。manager由非423HTTPException传播得到的失败history也必须检查。
- Console保留各catch error/info frame、resize容错、history/input/send timeout、断连关闭与reader先结束再close socket/client；profile SSE保留terminal error shape、短DB session及finally cancel/gather fetch tasks。
- 真实已建snapshot后分别制造forget HTTP423、非423HTTPException、普通Exception，保留snapshot真实存在和data bytes、同execution ID SKIPPED/FAILED/COMPLETED、count一次/ended_at/messages，以及up-skipped/down/up通知语义。
- notification HTTPError/普通Exception在COMPLETED/SKIPPED/FAILED三条路径都不改变原结果；安全down msg与原备份异常类型/重抛保留，context不留URL；取消通知必须传播而非被best-effort捕获。
- 取消backup/forget/notification与skin worker边界维持CancelledError，manager-owned process/work先drain再durable终态；skin失败不撤销已commit join/session/event，profile/WS观察者关闭完成消费者结算。
- cron400/404/409/423/500和原string/structured所在边界固定；ValidationError.msg与adapter ValueError/HTTPException原文不可仅凭类名当authored safe。
- 扩展owned API E2E及e2e/docs/coverage.md验证可达错误、真实副作用和应用日志；本轮没有执行，不能以unit callback/mock count代替部署证据。CN-04只有后续独立实施时才能调整被明确移除能力的测试。
- 保留成功调用无失败日志/无动态prefix或参数诊断求值；安全替换不把原 sig.bind/prefix 格式化前移到原func之前或成功路径。
- 同步和异步分别使 get_logger/current_runtime 获取失败，确认原异常传播且原func尚未执行；有绑定runtime时日志仍写入该runtime所属logger，不引入隐式default/global实例。

## E2-01: 修复 E2E 配置与世界别名预期对象污染

对每次GET使用独立零值DTO，严格分开draft、ack、首次persisted baseline、invalid PUT后的actual、restart actual及reset actual。stored只保存不会再被解码/修改的baseline。世界两个alias响应使用相同具体local DTO类型的独立新变量，绝不浅复制首次结果。增加针对真实业务检查函数的可控HTTP反例：400但实际值变化、GET缺已请求字段、同长度Teams/Players字段变化应失败；expected来自独立手列payload。不要只测试stdlib DeepEqual已知性质；必要时从suite提取具体比较函数以使回归能覆盖实际oracle，但不改全局Client.JSON、不用通用deepClone框架。

Validation:

- 保留所有模块valid/invalid/restart/reset，valid ack与持久读取一致。
- 保留真实claims/player-locations别名一致；补同长度坐标/身份/cluster字段错误反例。
- 补missing字段不能继承旧值，预期baseline自身必须不变。
- 定向affected real case正常/--no-reuse及必要Go格式/vet；最终最新SHA完整qualification。

## E2-02: 合并重复 full self-check，按创建ID验证历史

保留一次完整full RunTask，把第二段唯一额外的ID非空检查并入首段，删除已被强覆盖的重复请求。收集full与每single的实际ID；重启后遍历分页检查这些ID存在、无重复且各detail对应正确scope/check，保留limit/offset非法、missing ID和current_state断言。若environment已有启动/调度历史，以created集合包含关系及total/pages一致性核对，不盲目要求历史总数恰为当前创建数。修正文档“stream执行”描述，case ID是否改名按目录兼容/coverage计划决定；本项不扩成新的历史框架。

Validation:

- 完整catalog、dependency passed/restic warning、findings=result/detail、所有single项保留。
- 分页offset/limit、重启后ID/详情保留、invalid查询404/422与current health均保留。

## E2-03: 过滤结果验证精确身份与数量一致

每个file query手列带/的搜索根相对path及name，比较身份集合、duplicate和total_count=results长度；保留零匹配case为空集合。不要用过滤实现算expected或引入排序契约。snapshot无过滤期待全部3个已建ID，server过滤期待paths+server，server/path覆盖过滤按现有3个覆盖source集合；核对真实ID集合并拒绝重复。若出现额外环境snapshot，先确认Fresh基线/业务scope而非缩松断言。

Validation:

- 保留9个过滤输入/所有错误状态；同count错path、wrong name、重复结果必须失败。
- 保留global/server/path listing、snapshot delete/ignored/path-confinement；同count错ID必须失败。

## E2-04: 统一当前候选的 task 等待循环

先补当前task的characterization：假HTTP request边界与可控time，pending/running→completed、failed/cancelled和timeout，独立手列错误文本。让task方法拥有一个等待循环，keyword参数只表达现有timeout与错误label；snapshot_task调用它并传180s/snapshot，再解包id；recovery默认120s/recovery保持。deadline从受理返回后开始、200ms间隔、未捕获HTTP/KeyError的原发生时机都保持。旧release同步snapshot和历史archive SSE路径保留。

Validation:

- 新增202不是完成、pending/running完整结果、failed/cancelled、deadline/原文案。
- 保留checkpoint ownership原测试、真实部署升级/legacy rollback与current snapshot/recovery journey。

## E2-05: 只共享 multipart 编码，业务发送与断言留原suite

在internal/api或fixtures新增具体multipart body编码helper，输入ordered file parts（filename/[]byte，字段只保留实际files或显式field），返回bytes与content type及原error。3个caller各自准备parts并继续使用Do/Expect/结果解码。保留duplicate filename/恶意路径/二进制内容表示能力和caller顺序；map旧迭代无排序契约，不新加稳定排序。不共享session、overwrite policy或结果期望，不再造multipart transport client接口/registry。

Validation:

- 保留never/always/per_file/reusable与实际内容；malicious multipart整批拒绝且safe文件原bytes。
- 保留JAR metadata与world423 nooverwrite/无新file。
- 小编码测试以stdlib reader核对手列filename/bytes/重复parts，不只mock writer调用。

## E2-06: 仅合并现有固定压缩工作量；撤回无测量的暂停方案

在archive suite内提取一个具体固定workload生成器，保留260000、seed前缀与exact bytes两caller差异，权限suite仍只构造一次复用内容。保持现有大输入、active断言、cancel-vs-dismiss、权限副作用与最终worker/partial output检查。撤回本轮缩小输入、导入world pauser或新增100–200行进程控制夹具。若后续要可靠性优化，先在独占真实runtime做定向phase measurement，记录受理/active/permission probes/cancel/worker exit及多环境completed-before-cancel证据；仅得到证据后提出单独方案。不能通过重试业务到成功隐藏竞态。

Validation:

- 所有匿名/invalidcookie/missingCSRF拒绝后业务最终完成及completedTask原状态不变。
- owner/admin真实cancelled、dismiss后retained终态、无partial archive、worker终止/owned cleanup保持。
- fixture改动至少独立byte长度/seed样本核对并定向真实case；不因大型fixture而删race保护。

## E2-07: 空文件 oracle 区分缺失/null与真实空内容

在CheckFile当前零值response将content改为*string，要求非nil后比较exact string；missing和null返回清楚测试错误，非string保留UnmarshalTypeError。针对实际helper用HTTP fixture验证{}、null、wrong type、合法empty、普通UTF8内容，不泛化所有DTO。空文件restore补owned路径下文件存在、为普通文件并size=0的独立断言（或真实download bytes+existence），随后rollback回缺失的当前业务保持。

Validation:

- 合法content空串通过；{}、null、numeric失败，普通内容byte精确。
- 恢复empty文件实际存在零bytes；rollback按原场景回不存在；ignored、extra deletion与ordinary content保持。

## CI-01: OCI layer流式校验属于perf候选，未证实OOM

单列perf改进：manifest/config仍读小JSON并完整校验；layer以bounded chunks流式hash并计实际byte数量，只返回验证结果。共享现有DIGEST/regular-member/missing-member及mismatch错误边界，不添加OCI service层，不用descriptor或TarInfo size替代实际payload读取。archive整体file_digest保持。先加真实含layer tar fixtures（合法、payload digest错、descriptor size错、missing/nonregular），再在相同synthetic大layer与相同进程环境量测峰值内存，报告实测而非声称OOM或承诺百分比。

Validation:

- 保留全部release gate/source/metadata/registry-before-effect拒绝断言；加layer tar验证及损坏边界。
- 内存量测是定向benchmark，不运行全仓库测试、不启动registry或外部写入。

## CI-02: 用标准深复制代替 JSON 往返

引入copy.deepcopy，将supplied分支的JSON往返替换为deepcopy(supplied)。保留每次iteration新副本、删除missing gate与其他fault的顺序，最终successful receipt仍用未修改supplied。不要扩大到receipt校验或registry行为。

Validation:

- 保留failed/cancelled/skipped/missing gates不得registry write的现演练及release-gate测试；若提取小receipt helper可定向验证循环前后原对象相等，不写mock调用顺序测试。

## TC-04: 地图fanout验证坐标与取消后的幸存成功

增强原batch节点为固定每坐标PNG路径与对应future断言，事件乱序排出以区别position与coordinate。原same-key cancel节点改controlled events：两个消费者先注册并保持等待，cancel一个，随后发该坐标rendered并正常结束proc，要求剩余consumer成功且只有一次render/MCA。finally释放gate、join consumer/driver并await queue.close；fixture结束前关闭独立queue。missing-event fallback留现专属error节点，不用它代替success证据。

Validation:

- 保留single success/coalescing/missing/error/missing-event、last consumer kill、different key partial cancel、真实process owner/cleanup/lease场景。

## TC-05: 完整 argv 观测即可，不再造测试用 CLI parser

复用write_fake_mcmap，shell用NUL分隔每个真实参数（或短Python脚本JSON序列化sys.argv[1:]）；测试decode后按固定CLI契约对完整列表或精确flag-value配对断言。保留--json、所有必需/optional flags与单个坐标串边界。现download/palette/prune/replace/remove参数节点用带空格中文路径，palette多个-p与render多个-r以明确固定列表验证。fake继续提供声明events，不编写通用test CLI parser；一份精确argv断言已足以拒绝合并/错位flags，不重复同算法验证两遍。临时script/args文件在finally清理。

Validation:

- 保留NDJSON合法/非法/error/exit/cancellation/reaping；保留level_dat include/omit、threshold/mode/claims/dry-run、empty/single coords。
- 原argv节点增强完整参数分组；路径空格/中文和重复pack/region flags有固定预期。

## TC-06: 子路径压缩验证实际成员与未选数据隔离

增强原binary(7z) subtree节点：固定plugins/plugin.jar成员与原始bytes存在，config.yml/test.txt不在该archive内；使用7z成员list/extract业务断言，不从生产source_path算expected。独立/test.txt两份archive分别提取test.txt并断言first/second contents，保留第一份bytes不变、独立输出路径和size。扩展现API E2E子路径压缩/下载的成员选择覆盖及coverage记录，复用已有owned环境和工具；保留原root/whole-project roundtrip。root与subtree不同member根必须明确，不把plugins archive误按whole-project population规范重写。

Validation:

- 保留progress-before-process-exit、existing archive保留、PID cancellation/partial cleanup、atomic owned-stage、root E2E roundtrip。
- 原subtree/single-file节点增强成员/content/未选数据断言，不增重复格式魔数测试。

## TD-04: 并发玩家测试证明先创建再关闭

优先原位加强两个case：join之后fresh session验证正确player/server generation唯一open row，记录row ID；重复leave/stop后验证同row关闭、精确duration、不增重复rows。五人场景先明确五条open row，十次stop后同五row仅关闭一次。可将场景迁入test_service.py真实owner fixture，但只有保留double service join和repeated server stop输入后才删旧节点；保留独立连接barrier、100 players/multiserver压力场景。

Validation:

- one committed open row before leave；five rows before stop。
- same row IDs、correct generation/name/uuid、closed duration保持、repeated stop不重复。
- skin workers在DB/session patches关闭前drain。

## TD-05: 删除无断言 empty smoke，先补实际配置替换

删除358空smoke，保留reconciliation:247。先新增typed DNSManagerConfig变化case，用可观测旧/新stateful adapter factory和捕获构造参数，真实manager.initialize/update触发provider credentials/domain或router URL替换，确认旧client关闭、新adapter实际产生期望records/routes，失败provider时独立router仍可用；无需真实云调用。此覆盖成立后删除779内部调用烟测并合并只证明相同handoff的hash tests。保留disable/re-enable、未知库存不删除和partial writes settlement。

Validation:

- typed credential/domain/router URL变更后新adapter真正执行正确write，旧adapter不再写且关闭。
- 无关planning-only TTL/addresses变化不不必要重建但实际输出刷新。
- empty addresses/servers已有状态保留、disable零写/re-enable、init/close失败retention及下一action恢复。

## TD-06: 皮肤 handoff 测试观察真实数据库结果

在test_service.py的真实owning runtime/session fixture增加new/existing参数化handoff场景：gate skin client response但不替换update_player_skin/spawn，join完成后独立DB查询已提交session/event；观察skin实际start，release并等待runtime-owned work完成，fresh session验证正确UUID/player ID下skin/avatar/last_update保存。添加skin失败scene确认join/session/event不撤销且皮肤旧值保持。只有此完整链覆盖后删两个mock-only scheduled case；保证所有gates finally释放且runtime drain在数据库/monkeypatch teardown之前。不要把辅助皮肤改阻塞join。

Validation:

- new/existing正确身份参数、join committed/event先于skin、skin gate期间join已完成。
- 真实DB skin/avatar/last_update fresh-session输出，失败保持joined session与旧skin。
- owned background任务结束/取消及fixture drain，不只assert_awaited。

## TF-02: 独立修复 Cron 0/空串被旧闭包覆盖

以真实受控wrapper或实际builder/dialog先新增5→0、range起点0、interval非0→config.min、raw清空回归，检查父表达式和真实请求值，而非只检查局部input显示。最小修复将显式params字段存在性与合法0/空串分开，保留未传参数时旧draft fallback；不要全局改parse/clamp/空数字输入/weekday解释。optional秒0也覆盖。作为独立fix在FE-06前实施，原函数探针只是定位证据，实施后的UI测试才确认端到端结果。

Validation:

- 保留preset不submit；受控minute/hour/weekday/seconds从非0归0、范围/interval起点0。
- raw清空→再输入→visual往返、未传参数的mode draft、disabled、真正create/update cron字段。

## TF-03: 独立修复目录勾选完整集合丢更新

新增真实MultiFileUploadDialog+ConflictTree嵌套目录互动和最终HTTP per_file policy oracle，保留目录外选择。修复一次目录操作以所有leaf集合一次更新并只发完整array，单file也走同明确集合操作；或父级明确接delta并functional merge，但不能保留每leaf从旧whole-set覆盖。默认all-selected目录取消必须全部overwrite=false，空目录选择必须全部true，半选/深层/同名路径各自正确。点击开始上传验证真实发送policy，未选路径原bytes由ownedbrowser/API场景验证。与FE-09纯tree提取独立commit。

Validation:

- 保留queue/1000+1/reusable/abort/late/earlierwrites。
- 目录全选/反选/半选、nested descendants、outside state、same basename不同path、expand/collapse不改政策。
- 真实start上传HTTP逐路径决策准确；取消选择的已有文件bytes保持，不能仅断言callback调用次数。

## TF-04: 补文件夹上传身份与实际 multipart 字节 oracle

修正batch mock按webkitRelativePath||name返回实际path身份，保持原flat case。另建真实hook+fileApi+HTTP boundary integration，手工创建dir-a/config.toml与dir-b/config.toml不同bytes，显式设置webkitRelativePath。assert check请求手列目录/文件path、multipart两filename和bytes、不同success/skipped/failed result身份；不调用生产tree builder计算expected。增加树/dialogUI路径测试与TF03/FE09互为覆盖，但本项只测试/fixture改动。

Validation:

- 保留1000+1/zero-byte/reusable/abort和earlier writes失效。
- 同basename跨目录独立path/bytes、nested check、per_file full path、mixed results；错误flatten实现必须使新oracle失败。

## TF-05: 保留上传生命周期替身，补真实 hash 与发布等待 oracle

保留原可控lifecycle unit套件，不把所有mock换成重型真实组件。新增专属hook integration使用真实hash-wasm与真实waitForTaskResult，HTTP边界可控，fixture通过TextEncoder或忠实Blob读取返回原字节。abc固定公开SHA256作为独立oracle；同长度不同bytes给server digest，verify不得受理、session清理被请求；缺sha256也失败。publish task running/progress100不complete，completed才invalidate/完成，failed/cancelled/503重连保持真实waiter行为。本地abort、hashunmount detach与显式close cancel区别要保留。无需为了测试export私有hash函数、生产test flag或默认新增Docker journey。

Validation:

- 保留serial queue/drop isolation/pause offset/retry timers/unmount late/reopen与hash detach。
- abc bytes→固定hash，verify参数精确；mismatch/缺hash不publish且清理。
- publish pending/running/progress100/failed/cancelled/503→恢复、abort后不verify；缓存失效/phase真实结果。

## TF-06: 退出测试触发真实清理路径，保留跨session隔离

把原用例名改为重新挂载不同session隔离，保留next-login Query数据；删除仅证明测试自己clear的assert。另通过真实App/Sidebar退出按钮或AUTH事件触发生产清理，assert旧user/server/operation cache消失、后续登录读新owner数据、旧观察不继续产生effect。若专测Observer query-removal监听，保持同实例并实际remove operation query，再观察同ID terminal对应的外部feature refetch；不要断言内部handled集合。AUTH事件后的同实例dedup测试仅在真实调用路径需要时做，不把人为挂载寿命作为新契约。

Validation:

- 不同session key和nextlogin发现保留。
- 真实logout/401失效清旧cache、freshlogin新数据、停止旧观察。
- Observer operation-query removal后的真实资源刷新；browser cookie/401/socket不重连保留。

## Rejected consolidations

ST-07: strict file ownership and best-effort map ownership retain their distinct contracts.

DM-05: template port discovery and conflict detection retain their distinct partial-result/error behavior.
