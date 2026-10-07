## Why

全局刷新观察器反复读取完整操作列表，传输大量相同历史记录。使用有界内存变化通知减少重复传输与空闲轮询，同时在断线、后端重启和通知淘汰后恢复业务视图一致性。

## What Changes

- 新增认证的轻量游标增量读取，操作提交后发布刷新所需的变化信息。
- 在应用 runtime 中保存有条数和数据量上限的变化队列，游标绑定本次实例；无法补齐通知时明确要求重新同步。
- 全局观察器按批合并刷新，更新地图图片版本，并按活动状态调整轮询和处理隐藏、重连及登录会话边界。
- 保留操作历史、恢复处置、任务结果持久化和原有用户结果展示；不引入数据库迁移、外部消息服务或 Docker 部署模式变更。

## Capabilities

### New Capabilities

- `operation-refresh-sync`: 有界增量刷新通知、游标重置、认证和跨页会话同步。

### Modified Capabilities

无；既有终态同步与持久化结果要求继续适用。

## Impact

涉及 backend operation journal 提交边界、runtime 归属和新增 GET `/api/operations/changes`，frontend 全局观察器与地图缓存版本，定向单元/集成测试、API E2E 和当前架构文档。既有 operations 列表、详情、处置及 tasks API 保留；数据库、配置和 Docker 契约保持兼容。
