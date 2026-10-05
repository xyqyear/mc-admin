# 实施基线

本清单保留迁移前的契约与测试基线，表中的旧接口不代表当前可用路由；最终行为以主规范和组件文档为准，实施与验证状态见 tasks.md。

## 入口、调用方和交互

| 现有入口 | 后端归属 | 必须同步迁移的调用方 | 保留的交互规则 |
| --- | --- | --- | --- |
| POST /snapshots | snapshots 路由、SnapshotApplication | backups 命令/页面、FileSnapshotActions；snapshots、servers、Minecraft、system E2E fixture | 创建按钮等待真实完成 |
| POST /snapshots/restore/preview | snapshots 路由、SnapshotService | backups 命令、FileSnapshotActions；snapshots/world 文件范围 E2E | 预览期间保持加载；预览仍可跳过 |
| POST /snapshots/restore | SnapshotRestoreService | 共享恢复请求控制器、FileSnapshotActions；snapshots/world 文件范围 E2E | 文件快照对话框在恢复期间禁止关闭 |
| GET /snapshots、/repository-usage、/locks | snapshots 路由 | backups 查询/页面、文件快照选择器；snapshots/system E2E | 保留列表、过滤和仓库状态读取 |
| DELETE /snapshots/{id}、POST /snapshots/unlock | SnapshotService | backups 命令/页面；snapshots/world 恢复 E2E | 等待真实结果；原有解锁对话框允许关闭 |
| POST /servers/{id}/world-restore/snapshots | world 路由、SnapshotApplication | world 恢复命令/侧栏；world E2E helper | 世界/维度创建等待完成 |
| POST /servers/{id}/world-restore/eligible-snapshots | world 路由 | world 恢复查询、SnapshotPicker；world E2E | 按选择查询，不写在线目标 |
| POST /servers/{id}/world-restore/preview | WorldRestoreOrchestrator、预览应用 | useRestorePreview、RestorePreviewModal；world 预览/恢复 E2E | 准备中允许关闭；关闭观察不再隐式取消已受理工作 |
| 预览 heartbeat、DELETE、tile GET | PreviewSessionManager | useRestorePreview、PreviewTileLayer；预览 E2E | 保留心跳、TTL 和会话归属 |
| POST /servers/{id}/world-restore/restore | 世界恢复应用/范围执行器 | useRestorationStream、SnapshotPicker；world 恢复/空范围/维护/断线 E2E | 执行期间选择器禁止关闭 |
| GET restorations/detail、POST rollback | 世界恢复存储/应用 | RestorationHistoryDrawer；world 恢复/代次/旧数据 E2E、deployment_rehearsal.py | 回滚期间历史抽屉禁止关闭 |
| 定时备份和保留策略 | cron/jobs/backup.py | cron 测试及 API E2E | 独立执行历史、skipped 结果；复用公共业务服务 |

世界布局、维度名称、领地、玩家位置、地图读取和区块裁剪保留各自职责。任务观察和取消复用现有任务 API。跨页面刷新由 OperationObserver 负责。

迁移还涉及后端路由测试、runtime 工厂测试、架构边界检查、前端恢复集成测试、浏览器 fixture、敏感信息脱敏和操作恢复 E2E。删除旧路由前全局检索调用方；测试改为等待真实任务终态，同时保留原有内容和状态断言。

## 业务验证分工

| 行为 | 现有基线 | 需要补充的证据 |
| --- | --- | --- |
| 全局/项目/data 范围与路径限制 | snapshots 路由、文件范围与维护测试 | 显式范围、父子去重、别名占用、同名实例替换 |
| 当前和源快照排除规则 | 使用真实 Restic 的服务/规划测试 | 冻结规则、安全快照与区块写入保护、全部排除与有效缺失的区别 |
| 缺失内容与可逆回滚 | world 空范围、附属目录、范围往返测试 | 普通文件历史、回滚链、回滚前保存当前状态 |
| 世界/维度/区域/区块数据 | 使用真实 mcmap 的 world 集成测试 | 跨入口一致性、被忽略的 .mca/.mcc/附属文件 |
| 区域缓存正确性 | PNG 失效测试、地图 E2E | 仅 MCC 变化、删除、负坐标与跨区域、无关瓦片和调色板/JAR 保留 |
| 等待与观察生命周期 | 前端流式控制器/侧栏/历史测试 | 受理不等于完成、读取失败、刷新重连、显式取消 |
| 资源冲突与服务器删除 | world 维护与任务回归 | 已受理/排队/全局快照任务拒绝删除；可取消裁剪仍等待收尾 |
| 活跃仓库依赖 | 快照锁与保留策略 E2E | 删除与恢复/预览竞争、终态释放 |
| 数据库升级与重启 | 迁移绑定测试、旧数据/代次 E2E | 逐字段保留旧记录、缺失安全快照、中断状态、不猜测身份 |

历史样本使用 revision 2026092503 的临时数据库，包含成功、失败、中断、运行中、缺失安全快照、缺失目录、归属歧义，以及同名新实例对应的旧代次记录。先读取升级前的数据，再通过数据库和应用存储检查身份及恢复证据；不只断言版本号。
