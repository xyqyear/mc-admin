## Purpose

为玩家查询、RCON 和服内消息选择运行镜像已有的限时工具，通过直接容器执行减少等待开销，同时保留现有权限、查询结果、失败降级和命令参数语义，明确限时工具本身的终止边界。

## ADDED Requirements

### Requirement: Use the running container's timeout

系统必须（SHALL）优先使用存在的 `gnutimeout`，不存在时回退 `timeout`，不验证实现或版本，不缓存选择结果。选择必须（SHALL）在业务命令执行前完成，业务失败不得（SHALL NOT）触发工具回退或命令重发。

#### Scenario: 镜像提供不同命令名
- **WHEN** 当前镜像提供 gnutimeout，或仅提供 timeout
- **THEN** 优先使用前者，否则使用后者，接受工具自身的检查延迟，不要求 GNU 实现

#### Scenario: 工具缺失
- **WHEN** 两个候选都不存在
- **THEN** 命令失败，不执行无限时的业务命令，不自动安装依赖

#### Scenario: 容器被重启或替换
- **WHEN** 已选择的运行实例改变
- **THEN** 拒绝旧目标执行，不自动改投新实例或重复提交

### Requirement: Preserve standard timeout behavior

系统必须（SHALL）保留 Query 的已保存执行限时和 RCON 的 10 秒外层预算（容器内 8 秒及一秒强杀宽限），采用所选 timeout 的默认进程组终止语义及一秒强杀宽限；允许实现自身的检查延迟。零、负数或非有限限时不得（SHALL NOT）变成无限执行。

#### Scenario: 正常完成或普通查询管道超时
- **WHEN** 命令正常完成，或普通 Query 管道在原进程组内超过期限
- **THEN** 及时返回实际结果，或按 timeout 的信号与退出状态处理超时
- **AND** 不停止或重启 Minecraft 容器

#### Scenario: 被监控主命令忽略 TERM
- **WHEN** 主命令在超时 TERM 后仍保持运行
- **THEN** 由限时工具在一秒宽限后发送 KILL，结果不被报告为成功

#### Scenario: 后代脱离进程组或主命令提前退出
- **WHEN** 后代主动离开原组，或主命令已经退出但留下后台后代
- **THEN** 遵循 timeout 的标准处理，不承诺额外回收全部后代，也不启动宿主机进程扫描

### Requirement: Preserve query and command results

系统必须（SHALL）保留 Query 优先、必要时 RCON 降级、成功空列表与未知观测的区分，以及 RCON 输出、消息行序和既有错误分类。失败或结果不确定不得（SHALL NOT）导致自动重发 RCON。

#### Scenario: Query 失败后降级
- **WHEN** Query 明确失败或超时，当前实例仍可查询
- **THEN** 按既有规则使用 RCON，成功空列表是有效结果，双失败不批量标记玩家离线

#### Scenario: RCON 和多行消息
- **WHEN** 命令或消息包含中文、引号及 shell 特殊字符
- **THEN** 保留参数与输出，消息按非空行顺序发送，中途失败不重发已提交的行

### Requirement: Preserve authorization and execution-time checks

系统必须（SHALL）保留现有认证及服务器可执行状态校验，使用实际运行容器而非监控缓存授权。公开错误及新增执行诊断不得（SHALL NOT）泄露凭据、原始命令或原始 stderr。

#### Scenario: 未认证或目标不可执行
- **WHEN** 未认证客户端提交命令，或目标不存在、不健康
- **THEN** 按既有规则拒绝请求，不产生业务执行；已认证请求保留 404/409 分类

#### Scenario: 执行失败或结果不确定
- **WHEN** 容器命令失败、超时或连接异常
- **THEN** 保留安全的 502/504 等错误分类及阶段、退出码、耗时信息，不把部分输出或断线解释为成功

### Requirement: Observation cancellation does not imply remote termination

系统必须（SHALL）将本地调用生命周期与已经启动的容器命令区分。排队取消不得（SHALL NOT）启动业务命令；开始后的取消或断线不得（SHALL NOT）声称远端命令已立即终止或游戏副作用已撤销。已启动命令由 timeout 按其标准期限继续管理。

#### Scenario: 取消、关闭或后端失联
- **WHEN** 观察请求取消、应用关闭或控制连接丢失
- **THEN** 不启动后续降级或自动重试，正常关闭排空本地工作后释放连接资源
- **AND** 远端是否停止按实际证据报告，不用关闭连接代替停止确认

#### Scenario: 慢命令期间读取监控
- **WHEN** 一次命令正在等待结果
- **THEN** 不阻塞事件循环、独立监控及健康读取
