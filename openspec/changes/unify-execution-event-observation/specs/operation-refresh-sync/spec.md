## REMOVED Requirements

### Requirement: Activity aware polling

**Reason**: 同一认证事件流提供即时变化通知和有界游标恢复，无需周期 HTTP 读取。

**Migration**: 前端通过共享事件流携带最近已处理位置，成功处理每批变化后才推进位置。

## ADDED Requirements

### Requirement: Streamed operation refresh observation

前端必须（SHALL）通过共享认证事件流观察操作变化，不使用周期 HTTP 轮询。积压必须（SHALL）连续传输；成功处理刷新批次后才确认继续位置。断线或读取失败不得（SHALL NOT）推进位置或推断操作完成；重新连接必须（SHALL）使用已确认位置，并保留现有容量淘汰及重启后的明确重置语义。会话结束必须（SHALL）关闭订阅，禁止迟到批次写入新会话。

#### Scenario: 空闲后发生变化
- **WHEN** 空闲观察者连接期间新的管理操作结束
- **THEN** 观察者收到对应变化，无需等待周期 HTTP 读取

#### Scenario: 批次处理时断线
- **WHEN** 业务读取取消或刷新处理完成前连接中断
- **THEN** 未成功处理的批次不会被确认为已处理
- **AND** 重连从最近已确认位置继续，重复变化不会重复执行管理操作

#### Scenario: 隐藏或离线后恢复
- **WHEN** 浏览器在隐藏、离线或连接失败后重新建立观察
- **THEN** 从已确认位置恢复或明确重置，不丢失期间的业务变化

#### Scenario: 定时任务产生业务变化
- **WHEN** 定时任务产生现有操作变化
- **THEN** 原业务缓存刷新仍通过共享变化通知生效
- **AND** 定时任务自身的进度及日志传输行为保持原有契约
