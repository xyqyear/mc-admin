# 后端文档

先读[后端执行规则](../AGENTS.md)，再按任务选择下列主题。
跨组件流程见[项目文档](../../docs/README.md)，真实 API 场景见[E2E 覆盖](../../e2e/docs/coverage.md)。

## 架构、开发与验证

| 文档 | 内容 |
| --- | --- |
| [architecture.md](architecture.md) | 模块地图与依赖方向 |
| [runtime.md](runtime.md) | 应用构建、配置路径与生命周期 |
| [administration-contracts.md](administration-contracts.md) | 管理接口的兼容边界与回归归属 |
| [testing.md](testing.md) | 定向测试、fixture 与能力隔离 |
| [test-planning.md](test-planning.md) | 后端 CI 分片、耗时和覆盖审计 |
| [database-migrations.md](database-migrations.md) | 迁移操作、修复与验证 |
| [database-schema.md](database-schema.md) | schema revision、数据含义与降级保护 |

## 执行、配置与服务器

| 文档 | 内容 |
| --- | --- |
| [operations.md](operations.md) | 操作 journal、资源占用与增量通知 |
| [operation-recovery.md](operation-recovery.md) | 中断恢复、人工解除阻断与部署所有权 |
| [background-tasks.md](background-tasks.md) | 持久任务、终态、取消和结果 |
| [non-snapshot-operations.md](non-snapshot-operations.md) | 非快照管理操作与任务接口清单 |
| [servers.md](servers.md) | 服务器身份、生命周期和删除准入 |
| [minecraft.md](minecraft.md) | Docker Compose、端口与资源监控 |
| [monitoring.md](monitoring.md) | 共享采样、指标口径、新鲜度与监控接口 |
| [configuration.md](configuration.md) | 配置版本、分阶段应用与源元数据 |
| [templates.md](templates.md) | 模板定义、快照与模式转换 |
| [dynamic-config.md](dynamic-config.md) | 动态配置、保存校验和迁移 |
| [cron.md](cron.md) | 计划、注册、执行和重启调度 |
| [self-check.md](self-check.md) | 自检目录、触发与持久结果 |
| [dns.md](dns.md) | DNS/router 观察与独立协调 |

## 文件、快照与地图

| 文档 | 内容 |
| --- | --- |
| [files.md](files.md) | 文件边界、搜索、压缩与目录导出 |
| [archive-upload.md](archive-upload.md) | 上传会话、摘要与原子发布 |
| [snapshots.md](snapshots.md) | Restic、范围、逻辑排除和快照备注 |
| [snapshot-restoration.md](snapshot-restoration.md) | 公共恢复、回滚、预览和历史 |
| [world-restore.md](world-restore.md) | 世界布局、区块适配与地图预览 |
| [chunk-prune.md](chunk-prune.md) | 裁剪预览、输入有效性与应用 |
| [server-map.md](server-map.md) | mcmap 初始化、瓦片与队列 |
| [ftb-claims.md](ftb-claims.md) | FTB 领地提取与几何 |
| [player-locations.md](player-locations.md) | 存档玩家位置与维度解析 |

## 身份、玩家与外部接口

| 文档 | 内容 |
| --- | --- |
| [auth.md](auth.md) | Cookie、CSRF、密码和动态码登录 |
| [audit.md](audit.md) | 审计与敏感信息保护 |
| [players.md](players.md) | 玩家身份/会话服务和生产者 |
| [player-identity.md](player-identity.md) | UUID 与在线身份解析 |
| [log-monitor.md](log-monitor.md) | 日志监听与玩家事件分发 |
| [websocket-console.md](websocket-console.md) | 控制台连接和消息协议 |
| [bot-integration-apis.md](bot-integration-apis.md) | RCON、消息、事件流和服务器概览 |

文档调整遵循[文档归属与维护](../../docs/documentation.md)。
