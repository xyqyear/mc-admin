# operation-consistency Specification

## Purpose

Keep normal server administration operations coherent from preparation through observable completion while preserving existing feature scope and practical recovery boundaries.

## Requirements

### Requirement: 服务器填充完整替换数据

系统必须（SHALL）在独立暂存目录完成解压与准备，再原子发布完整数据树。发布失败必须（SHALL）保留原服务器数据及源归档；不支持同盘原子交换时不得（SHALL NOT）退化为先删除原数据再逐项移动。成功发布后清理失败必须（SHALL）明确报告数据已替换。

#### Scenario: 发布目录失败
- **WHEN** 目录交换因权限、文件系统限制或空间不足失败
- **THEN** 任务失败，原数据与源归档保持不变

#### Scenario: 完整替换已有服务器
- **WHEN** 填充任务成功
- **THEN** 新数据和隐藏文件完整可用，旧树中的多余文件被移除，源归档按既有约定消费

### Requirement: Configuration preview and application agree
The system SHALL use the server's retained template snapshot for ordinary parameter preview and saving, and SHALL preserve explicit source-template upgrades and direct/template conversion.

#### Scenario: Source template changed or deleted
- **WHEN** a user edits a server whose source template has changed or been deleted
- **THEN** preview and saving use the server snapshot unless an explicit upgrade is requested

### Requirement: Configuration completion includes its metadata
The system SHALL report configuration task success only after required metadata corresponds to the applied configuration, and SHALL preserve whether the server was intended to be running.

#### Scenario: Edit after stopping
- **WHEN** a user stops a server and applies valid changed configuration
- **THEN** the configuration is applied successfully and the server remains stopped

#### Scenario: Startup fails after configuration is applied
- **WHEN** applying configuration succeeds but restarting the server fails
- **THEN** the task reports failure and the stored configuration source still corresponds to the applied configuration

### Requirement: Destructive world maintenance owns its server scope

**破坏性世界维护独占相应服务器范围**

系统必须（SHALL）在对世界进行破坏性维护期间阻止冲突修改和服务器启动，按受影响服务器范围协调定时备份，并保留普通文件在线恢复。该规则必须（SHALL）一致地适用于手动生命周期操作、定时操作、配置重建和服务器删除。已受理或运行中的快照创建、恢复和回滚必须（SHALL）阻止受影响服务器删除；可取消裁剪继续保留取消并等待写入停止后的删除行为。

#### Scenario: Start during pruning
**裁剪期间请求启动**

- **WHEN** 裁剪应用操作占用服务器时，用户请求启动该服务器
- **THEN** 启动被拒绝，并在维护结束后恢复可用

#### Scenario: Ordinary online file restore
**普通文件在线恢复**

- **WHEN** 正在运行的服务器恢复世界目录之外的普通配置文件
- **THEN** 在线恢复仍可使用

#### Scenario: Scheduled backup skips during maintenance
**维护期间跳过定时备份**

- **WHEN** 定时单服务器备份或全局备份无法取得其受影响服务器范围的占用权
- **THEN** 不创建快照，并记录终态为 `skipped` 的执行及原因
- **AND** 执行历史将结果显示为跳过，而非成功

#### Scenario: 重建与世界恢复竞争
- **WHEN** 配置应用和世界恢复同时作用于同一服务器
- **THEN** 两者存在冲突的阶段不会重叠执行
- **AND** 恢复操作占用世界期间，重建不能启动服务器

#### Scenario: 定时重启与维护竞争
- **WHEN** 定时重启到期时，冲突的维护操作正在占用该服务器
- **THEN** 重启不会绕过占用规则，其执行记录为已跳过

#### Scenario: 删除无法等待活动操作结束
- **WHEN** 删除服务器时，无法在有界等待时间内使允许取消的活动写入结束
- **THEN** 删除报告冲突，不删除服务器目录
- **AND** 成功等待已有操作结束后到实际删除之间，新提交的并发操作无法进入

#### Scenario: 快照任务已受理但尚未持有执行锁
- **WHEN** 快照创建、恢复或回滚已经受理，用户删除其影响的服务器
- **THEN** 删除报告冲突及任务原因，不自动取消该快照任务
- **AND** 全局任务同样保护其影响的服务器，删除进入排他阶段时再次确认冲突

#### Scenario: 可取消裁剪期间删除
- **WHEN** 仅有允许取消的裁剪任务影响目标服务器，用户请求删除
- **THEN** 系统停止该任务并确认写入结束后才删除服务器目录

### Requirement: Restore completion and cancellation are observable

**恢复完成及取消的结果可观察**

恢复必须（SHALL）由独立任务持有执行。观察连接断开不得（SHALL NOT）取消已受理的任务。显式取消或失败后，系统必须（SHALL）结束可终止执行并完成必要收尾，使已有恢复历史不再报告运行中。只有确认所属写入停止后，才可解除相应写入限制；无法确认时必须（SHALL）记录中断及原因并保留受影响范围的恢复阻断。选中的源世界数据必须（SHALL）在目标目录缺失时仍可恢复。

#### Scenario: Client disconnects during restore
**恢复期间客户端断开**

- **WHEN** 恢复期间客户端断开任务观察连接
- **THEN** 执行继续，用户重新连接后能读取任务进度和结果
- **AND** 安全快照及恢复记录仍保留可用的回滚引用

#### Scenario: Missing entities or poi directory
**缺少 entities 或 poi 目录**

- **WHEN** 选中快照包含附属目录数据，而整个目标目录不存在
- **THEN** 恢复包含该数据，回滚仍可恢复到原先目录缺失的状态

#### Scenario: 恢复断流后写入停止状态不明
- **WHEN** 用户断开观察后任务因显式取消或后端故障中断，且无法确认所属写入已停止
- **THEN** 操作日志记录中断及原因，已有恢复历史不再报告运行中
- **AND** 受影响范围内的冲突写入继续被阻止，完成恢复验证前不解除相应限制

### Requirement: Upload flows own their local activity and outputs
The system SHALL keep each upload flow's checking, batching, pause/resume and cancellation coherent, retain serial batch behavior, and give independent compression tasks independent output files.

#### Scenario: Repeated checking action
- **WHEN** conflict checking is still in progress
- **THEN** the same upload flow cannot start a second check-and-upload operation

#### Scenario: Separate compression tasks
- **WHEN** two tasks compress the same source within one timestamp interval
- **THEN** their output files are distinct

### Requirement: Deleted identities lose access
The system SHALL reject subsequent authenticated requests using sessions belonging to deleted users while preserving the master-token protocol.

#### Scenario: Deleted user keeps an open browser
- **WHEN** the user is deleted and its old browser session requests its identity
- **THEN** the request is unauthorized

### Requirement: Local configuration and file failures have bounded effects
The system SHALL reject newly submitted invalid template or log-parser definitions and SHALL keep unaffected directory entries visible when one entry disappears.

#### Scenario: Invalid parser definition
- **WHEN** a submitted rule cannot compile or lacks required extraction groups
- **THEN** saving fails with a validation error and the prior configuration remains effective

#### Scenario: Directory entry disappears
- **WHEN** a listed directory entry cannot be read because it no longer exists
- **THEN** other entries remain available

### Requirement: DNS manager honors the effective enabled state
The system SHALL perform no new automatic DNS writes after a disabled configuration is observed and SHALL settle each update's work before allowing a subsequent update.

#### Scenario: Hot disable followed by server administration
- **WHEN** enabled DNS management is disabled and a server lifecycle action occurs
- **THEN** that action causes no DNS or router writes

### Requirement: Player history remains usable across cleanup and recovery
The system SHALL preserve increasing chat replay identifiers across cleanup and SHALL not calculate negative playtime during crash recovery.

#### Scenario: Cleanup removes the highest chat identifier
- **WHEN** new chat arrives after cleanup removed the highest stored identifier
- **THEN** a client using its previous cursor can replay the new chat

#### Scenario: Join follows the last heartbeat
- **WHEN** crash recovery ends a session that began after the recorded heartbeat
- **THEN** the session ends no earlier than its join time and contributes nonnegative playtime

### Requirement: Finite progress flows terminate visibly

前端必须（SHALL）在依附请求的有限进度流缺少终态却结束时展示可恢复失败；独立任务的观察连接失败必须（SHALL）显示连接异常并继续观察，而不是推断执行失败或完成。

#### Scenario: Premature progress EOF
- **WHEN** 仍依附请求执行的有限流在完成前关闭
- **THEN** 用户看到可恢复失败，可以关闭或重试该流程

#### Scenario: 快照预览任务观察失败
- **WHEN** 快照预览任务的状态读取暂时失败
- **THEN** 原有阻塞继续，界面重试观察，不自动再次提交预览或结束任务

#### Scenario: 任务记录已过期或不存在
- **WHEN** 详情查询明确返回 404
- **THEN** 界面结束观察，提示刷新业务页面确认实际结果，不宣称任务已成功或无限重试

### Requirement: E2E phase budgets reflect actual work
The runner SHALL reserve capacity before starting the deployment deadline, let long streams use their operation deadline, and provide diagnostics and resource cleanup independent bounded budgets.

#### Scenario: Capacity queue exceeds setup duration
- **WHEN** a case waits for a Minecraft slot longer than its setup budget but remains within the run deadline
- **THEN** it receives its setup budget after capacity is acquired

#### Scenario: Diagnostic timeout
- **WHEN** diagnostics exhaust their deadline
- **THEN** resource cleanup still starts with an unexpired deadline and the diagnostic failure remains reported

### Requirement: Managed restart schedules use exact server identity

**受管重启计划按配置的服务器名称精确定位**

系统必须（SHALL）根据重启计划参数中的完整服务器名确定目标，在每次执行开始时定位当前同名服务器。显示名称、子串匹配和历史实例代次不得（SHALL NOT）决定计划归属或阻止有效计划注册。独立创建的 cron 任务必须（SHALL）保留现有灵活性。单次执行必须（SHALL）继续复核已捕获的实例身份并遵守资源冲突、暂停和取消约束。

#### Scenario: 服务器名称具有共同前缀
- **WHEN** 名为 `survival` 和 `survival2` 的服务器都具有受管重启计划
- **THEN** 对任意一台服务器计划的操作都不会改变另一台的计划

#### Scenario: 显示名称与目标参数不一致
- **WHEN** 名为 `restart-gtnh-1` 的计划参数指向服务器 `gtnh`
- **THEN** 计划按 `gtnh` 注册和执行，显示名称差异不产生归属错误

#### Scenario: 下一次执行遇到同名新实例
- **WHEN** 有效活动计划指向的服务器名对应当前的新实例
- **THEN** 新的一次执行按名称定位当前实例，不因历史代次或计划创建时间被阻止
- **AND** 已取消或暂停的计划不会自动恢复执行

#### Scenario: 历史上同名服务器具有多个受管计划
- **WHEN** 服务器页面读取或修改匹配同一目标名称的多个受管重启计划
- **THEN** 优先管理最早建立的未取消计划，全部取消时展示最新取消计划供用户明确重新启用
- **AND** 其他计划、原有参数、状态及执行历史不因选择或迁移被修改
- **AND** 独立创建的计划不被服务器页面接管

#### Scenario: 并发创建受管计划
- **WHEN** 同一服务器同时请求创建受管重启计划
- **THEN** 请求不产生额外重复受管计划

#### Scenario: 单次执行等待期间实例改变
- **WHEN** 一次执行已捕获目标实例，而该实例在获取执行资源前被替换
- **THEN** 该次执行不对替换实例调用 Docker
- **AND** 下一次符合触发条件的执行可以重新按名称定位当前实例

#### Scenario: 目标缺失或停止
- **WHEN** 定时重启触发时目标服务器未登记或已停止
- **THEN** 执行记录跳过及原因，不调用 Docker 重启

#### Scenario: 删除服务器取消活动重启计划
- **WHEN** 删除名为 `survival` 的服务器
- **THEN** 按参数取消目标为 `survival` 的活动重启计划，保留执行历史
- **AND** 不取消目标为 `survival2` 的计划

### Requirement: Concurrent player observations preserve one open session

**并发玩家状态观测只保留一个未结束会话**

系统必须（SHALL）为每个玩家与服务器身份组合保留至多一个未结束会话。对同一上线/离线状态的重复或并发观测不得（SHALL NOT）导致在线时长重复计算。

#### Scenario: 日志和在线校准报告同一次上线
- **WHEN** 日志跟踪与在线玩家校准同时观测到同一玩家在同一服务器在线
- **THEN** 该玩家与服务器组合只存在一个未结束会话
- **AND** 随后的离线仅计算一次该会话的时长

### Requirement: Editors retain authored drafts until success or deliberate discard

**编辑器保留草稿，直到保存成功或用户明确丢弃**

文件和 Compose 编辑器必须（SHALL）区分用户草稿与远端获取的内容。编辑器必须（SHALL）在初始内容可用前禁用保存，在保存失败时保留草稿，并避免因远端内容变化而替换已修改的草稿。使用版本感知保存的客户端必须（SHALL）在远端版本已变化时收到冲突，而非悄然覆盖。

#### Scenario: 文件加载完成前保存
- **WHEN** 文件内容仍在加载或加载失败
- **THEN** 编辑器不允许把空白或过时草稿作为已加载文件提交

#### Scenario: 文件保存失败
- **WHEN** 服务器拒绝保存文件或请求失败
- **THEN** 草稿仍可用于修正或重试
- **AND** 界面不会提示保存成功

#### Scenario: 与已经变化的远端 Compose 内容比较
- **WHEN** 存在未保存修改的编辑器为比较而获取到不同的远端配置
- **THEN** 保留用户草稿，并单独展示远端变化

#### Scenario: 并发的版本感知保存
- **WHEN** 版本感知保存应用前，另一名管理员改变了远端版本
- **THEN** 过期保存以冲突被拒绝，草稿继续保留

#### Scenario: 解决版本冲突
- **WHEN** 用户获取新的远端内容、与保留的草稿比较，并明确选择要保存的内容
- **THEN** 编辑器可以基于新观测到的版本提交该内容
- **AND** 若其间再次发生修改，则再次报告冲突，不悄然覆盖

#### Scenario: 旧客户端不提供版本
- **WHEN** 其他方面有效的旧保存请求没有提供预期版本
- **THEN** 请求在遵守操作占用规则的前提下保留现有写入语义

#### Scenario: 有意清空已加载文件
- **WHEN** 文件已成功加载，用户有意清空内容并保存
- **THEN** 可以通过现有编辑流程保存空内容

### Requirement: Completion updates visible state independently of the initiating page

**操作完成后的可见状态更新不依赖发起页面**

独立后台操作到达终态后，即使发起页面已经卸载，受影响的缓存视图也必须（SHALL）与服务器同步。发生部分修改后失败，也必须（SHALL）触发受影响资源的状态同步。

#### Scenario: 切页后重建完成
- **WHEN** 用户在重建期间离开 Compose 页面，并在完成后返回
- **THEN** 页面展示结果配置和状态，无需等待较长的缓存过期时间或手动刷新

#### Scenario: 已取消的操作已经修改数据
- **WHEN** 已取消或中断的操作已经产生部分修改
- **THEN** 受影响视图与这些修改同步，不把取消视为自动回滚

### Requirement: Error feedback matches the actual result

**错误反馈与实际结果一致**

界面必须（SHALL）保留有意义的服务端错误消息，一致地解释归一化错误状态，并仅在确实获取到新数据时报告刷新成功。有意跳过的定时操作必须（SHALL）显示为跳过，而非执行成功。

#### Scenario: 文件刷新请求失败
- **WHEN** 刷新文件列表失败
- **THEN** 界面报告失败，不显示成功通知

#### Scenario: 定时重启发现服务器已停止
- **WHEN** 定时重启因服务器已停止而有意不执行重启
- **THEN** 执行历史记录为跳过，并附带原因

### Requirement: 玩家资料失败保留可用地图

玩家资料有限流必须（SHALL）在没有终态的 EOF 或消费失败时显示可重试错误；已有资料缓存、玩家位置及地图必须（SHALL）保持可用。用户取消或离开页面不得（SHALL NOT）被展示为资料服务失败，资料错误不得（SHALL NOT）改变恢复或裁剪任务状态。

#### Scenario: 资料流提前结束
- **WHEN** 世界页面的玩家资料流在完成事件前结束
- **THEN** 玩家面板显示资料加载错误和重试入口，已缓存名称与位置保持可见

#### Scenario: 资料事件消费失败
- **WHEN** 一个可解析资料事件在消费者处理时失败
- **THEN** 当前流停止并释放读取资源，显示可恢复错误，不静默跳过或宣称完成

### Requirement: 安全错误保留上传与备份结果边界

系统必须（SHALL）在净化错误输出时保留普通上传的预检、执行期整批失败与逐文件失败边界，以及备份保留清理和通知的既有结果分类。取消必须（SHALL）继续传播，实际完成的文件或快照不得（SHALL NOT）被净化逻辑撤销。

#### Scenario: 上传预检后路径改变
- **WHEN** 上传路径通过预检后在执行期变为越界路径
- **THEN** 请求仍按执行期失败返回安全字符串的 500，越界目标不写入

#### Scenario: 单文件写入失败
- **WHEN** 批次中某文件写入失败
- **THEN** 该成员返回安全失败原因，后续成员继续按原策略执行，已产生部分字节保留

#### Scenario: 快照后的保留清理失败
- **WHEN** 已创建快照后保留清理返回维护冲突、其它 HTTP 失败或普通异常
- **THEN** 依次保留跳过、失败或警告后成功的原有执行分类，已创建快照保留
- **AND** 通知失败不会覆盖原业务结果，通知取消继续传播
