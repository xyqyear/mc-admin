## Purpose

为玩家查询、RCON 与服内消息提供及时、可核验的执行结果，并在超时、取消、后端失联和服务器实例替换时限定本次命令的作用范围，保留现有权限、玩家状态及管理安全边界。

## ADDED Requirements

### Requirement: Command results represent completed execution

系统必须（SHALL）在命令及必要收尾完成后返回实际输出和结果，不得（SHALL NOT）将已受理、连接关闭或部分输出解释为成功。正常完成不得（SHALL NOT）等待与实际工作无关的固定轮询间隔。

#### Scenario: 快速成功与非零退出
- **WHEN** 命令快速完成并产生输出，或产生部分输出后失败
- **THEN** 成功返回完整的既有业务输出，失败保留失败语义
- **AND** 不因尚未到达限时时间或固定检查周期而延迟正常返回

#### Scenario: 输出过大或流损坏
- **WHEN** 命令输出超过有界资源限制或传输无法完整解释
- **THEN** 系统结束本次执行并返回明确失败，不把截断输出报告为成功

### Requirement: Execution is bound to an authoritative server instance

系统必须（SHALL）在执行前验证当前服务器身份、运行实例和可执行状态，并将命令及其清理限定于该实例。监控缓存、公开名称或已过期的准备结果不得（SHALL NOT）替代执行时的校验。

#### Scenario: 准备后同名服务器被重建
- **WHEN** 命令排队或准备期间目标被删除、重建或重启
- **THEN** 旧命令失败，不在替换实例上自动执行或清理

#### Scenario: 进程身份被复用或归属不可验证
- **WHEN** 清理期间原进程已经退出且标识被复用，或系统不能证明目标归属
- **THEN** 系统不向无关进程发送终止信号，也不把无法验证解释为已经清理
- **AND** 无关 Java 服务和其他命令保持运行

### Requirement: Deadline and cancellation include real cleanup

系统必须（SHALL）为准备、执行和清理提供有限预算，使用当前有效的配置限时。超时、取消或关闭必须（SHALL）处理本次命令及属于它的子进程后再确认清理完成；仅停止观察不得（SHALL NOT）视为进程退出。命令作用于游戏服务器后的副作用不得（SHALL NOT）被描述为自动回滚。

#### Scenario: 查询阻塞并产生子进程
- **WHEN** 一次查询超时且其命令或子进程仍在等待，包含忽略普通终止请求的进程
- **THEN** 系统在有限清理预算内停止本次执行并确认退出
- **AND** 清理不停止或重启 Minecraft 容器

#### Scenario: 取消发生在命令放行之前
- **WHEN** 请求在执行所有权建立或业务命令放行前被取消
- **THEN** 业务命令没有副作用，准备工作和等待资源被回收

#### Scenario: 后端强制终止或控制连接失联
- **WHEN** 后端不能继续发送取消请求且容器内命令仍未完成
- **THEN** 本次执行仍有有限的停止边界，不留下无限等待的查询和失联保护进程

#### Scenario: 清理结果仍不确定
- **WHEN** 系统无法确认本次命令已经结束
- **THEN** 返回或记录清理不确定的安全失败，不报告成功或已完成取消
- **AND** 保留必要执行限制和既有持久化操作保护，不无限增加同一目标上的工作

### Requirement: Player queries preserve fallback and unknown observations

系统必须（SHALL）保留 Query 优先、必要时 RCON 降级的玩家列表语义；成功空列表与无法取得列表必须（SHALL）被区分。降级不得（SHALL NOT）掩盖未完成清理、应用关闭或目标实例变化。

#### Scenario: Query 成功返回空列表
- **WHEN** Query 成功确认没有在线玩家
- **THEN** 按现有玩家同步规则处理空列表，不把它判定为查询失败

#### Scenario: Query 超时后 RCON 成功
- **WHEN** Query 已确认超时且其执行已清理，而当前目标仍可查询
- **THEN** 使用 RCON 结果完成同步，不因第一次失败而报告同步失败

#### Scenario: 两种查询都失败
- **WHEN** Query 与后续 RCON 都没有取得可信结果
- **THEN** 本轮属于未知观测，不把全部玩家标记为离线

#### Scenario: 查询取消或目标改变
- **WHEN** 请求已取消、应用正在关闭、清理不确定或原目标已被替换
- **THEN** 不启动新的降级命令

### Requirement: Existing RCON and message contracts remain usable

系统必须（SHALL）保留既有认证、成功响应、命令参数和消息行序，以及不存在、不健康、执行失败和超时的错误分类。未经认证的调用不得（SHALL NOT）产生容器执行或游戏副作用。结果不确定时不得（SHALL NOT）自动重发已提交的 RCON 命令。

#### Scenario: 未认证或服务器不可执行
- **WHEN** 未认证客户端提交命令，或认证客户端指向不存在/不健康的服务器
- **THEN** 按既有规则拒绝请求，未创建业务执行且游戏状态不变

#### Scenario: 特殊字符和多行消息
- **WHEN** 已认证用户发送包含引号、换行、中文或 shell 特殊字符的命令或消息
- **THEN** 参数按既有契约传递，消息按非空行顺序发送，不产生 shell 注入或重复发送
- **AND** 中间行失败不重发已经提交的行

#### Scenario: 命令已提交但响应丢失
- **WHEN** 执行结果不能被确认，而命令可能已经被游戏服务器接受
- **THEN** 返回明确失败，不自动提交第二次，也不承诺撤销已经发生的游戏行为

### Requirement: Command work is bounded and isolated from monitoring

系统必须（SHALL）限制活动执行、等待者和输出资源，慢命令不得（SHALL NOT）阻塞独立监控及健康读取。关闭必须（SHALL）停止生产新工作、清理既有工作再释放依赖；重复取消不能跳过必要收尾。

#### Scenario: 一个服务器的命令长期无响应
- **WHEN** 一台服务器的命令正在等待或清理
- **THEN** 独立监控仍可采样，健康读取可完成，容量允许时其他服务器命令仍可执行

#### Scenario: 容量耗尽和应用关闭
- **WHEN** 执行达到容量限制，随后应用开始关闭
- **THEN** 不无限创建待处理工作，尚未放行的命令被拒绝或取消
- **AND** 已放行命令完成清理后才释放相关执行资源

### Requirement: Diagnostics are useful without exposing command contents

系统必须（SHALL）提供可区分命令类别、失败阶段、耗时、退出状态和清理结果的诊断信息，不得（SHALL NOT）在新增执行诊断中暴露凭据、原始命令模板或未脱敏异常内容。

#### Scenario: 预期查询降级
- **WHEN** Query 失败且已安全降级
- **THEN** 诊断可以识别退出或超时原因，按预期降级记录简短信息，不输出完整命令或原始异常堆栈

#### Scenario: 错误输出包含敏感内容
- **WHEN** 容器输出或传输异常中包含测试凭据、命令内容或登录数据
- **THEN** 公开错误及新增执行日志不泄露这些内容，仍能判断失败阶段和清理状态
