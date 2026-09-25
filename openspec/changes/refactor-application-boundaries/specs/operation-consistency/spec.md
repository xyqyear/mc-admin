## MODIFIED Requirements

### Requirement: Destructive world maintenance owns its server scope

**破坏性世界维护独占相应服务器范围**

系统必须（SHALL）在对世界进行破坏性维护期间阻止冲突修改和服务器启动，按受影响服务器范围协调定时备份，并保留普通文件在线恢复。该规则必须（SHALL）一致地适用于手动生命周期操作、定时操作、配置重建和服务器删除。

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
- **WHEN** 删除服务器时，无法在有界等待时间内使活动写入结束
- **THEN** 删除报告冲突，不删除服务器目录
- **AND** 成功等待已有操作结束后到实际删除之间，新提交的并发操作无法进入

### Requirement: Restore completion and cancellation are observable

**恢复完成及取消的结果可观察**

系统必须（SHALL）在恢复被取消、请求流断开或失败后结束可终止的执行，完成必要收尾，并使已有的恢复历史不再报告运行中。只有确认所属写入停止后，才可解除相应写入限制；无法确认时必须（SHALL）记录中断及原因并保留受影响范围的恢复阻断。选中的源世界数据必须（SHALL）在目标目录缺失时仍可恢复。

#### Scenario: Client disconnects during restore
**恢复期间客户端断开**

- **WHEN** 活动恢复流被关闭，且能够确认所属写入停止
- **THEN** 执行及必要收尾结束后释放维护占用，已有恢复历史不再报告运行中
- **AND** 若已经建立安全快照及恢复记录，保留其可用的回滚引用

#### Scenario: Missing entities or poi directory
**缺少 entities 或 poi 目录**

- **WHEN** 选中快照包含附属目录数据，而整个目标目录不存在
- **THEN** 恢复包含该数据，回滚仍可恢复到原先目录缺失的状态

#### Scenario: 恢复断流后写入停止状态不明
- **WHEN** 活动恢复流被关闭，但无法确认所属写入已停止
- **THEN** 操作日志记录中断及原因，已有恢复历史不再报告运行中
- **AND** 受影响范围内的冲突写入继续被阻止，完成恢复验证前不因流关闭而解除相应限制

## ADDED Requirements

### Requirement: Managed restart schedules use exact server identity

**受管重启计划使用确切的服务器身份**

读取、修改、暂停、恢复或删除服务器的受管重启计划时，必须（SHALL）定位到该服务器自己的计划。显示名称和子串匹配不得（SHALL NOT）决定归属。独立创建的 cron 任务必须（SHALL）保留现有灵活性。

#### Scenario: 服务器名称具有共同前缀
- **WHEN** 名为 `survival` 和 `survival2` 的服务器都具有受管重启计划
- **THEN** 对任意一台服务器计划的操作都不会改变另一台的计划

#### Scenario: 历史计划归属不明确
- **WHEN** 现有计划元数据无法确定无歧义的归属
- **THEN** 迁移或状态协调报告该歧义，不重新分配或删除无关任务

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
