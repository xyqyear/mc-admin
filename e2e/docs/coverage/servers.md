# 模板、服务器与 Minecraft 运行行为

本页记录已实现的业务断言；执行结果以当前 SHA 的资格运行证据为准。
返回[覆盖索引](../coverage.md)，用例扩展遵循[架构与隔离约定](../architecture.md)。

| 功能域 | 稳定用例 ID | 已实现的验证内容 |
| --- | --- | --- |
| 模板生命周期 | `templates.lifecycle` | 验证带类型变量的模板增删改查、Schema、渲染结果、非法变量拒绝和删除效果。 |
| 模板类型、默认值与端口 | `templates.types-defaults-and-boundaries` | 验证字符串、整数、浮点数、枚举、布尔值的 Schema 与替换；拒绝类型错误、越界值、缺少必填项、重复定义和未定义变量；模板和默认变量保存时拒绝非法正则、倒置范围及不符合约束的默认值，并保持原数据；默认值在重启后保留；建议端口避开现有游戏与 RCON 端口映射。 |
| 直接创建与模板创建服务器 | `servers.template-snapshot` | 验证直接创建、重复冲突、删除后按模板重新创建；删除源模板后保留服务器的模板快照；最终删除服务器。 |
| Compose 转换与重建 | `servers.compose-conversions-and-rebuild` | 验证 Compose 读取与编辑、变量提取、转换预览；内容相同的转换不触发重建，内容变化时重建任务达到终态且元数据立即一致；每次配置任务均核对停服状态及原运行意图；源模板修改或删除后，服务器快照预览与保存仍使用保留定义；显式升级采用新源模板，直接模式与模板模式转换及 Compose 持久化正确，未携带版本的既有请求仍可用。 |
| Configuration versions | `servers.configuration-versions` | Independent editors receive the same baseline; an accepted write changes the version and stale writes receive `configuration_conflict` with the current version without overwriting content. External Compose changes invalidate a previously observed version. Legacy saves remain accepted. Extraction/conversion previews carry the observed version; mode changes version their source metadata, and stale template/direct conversions are rejected. |
| Partial configuration failure | `servers.configuration-partial-failure-recovery` | A real owned Docker container runs a harmless sleep command, without game downloads. Applying an invalid executable fails container startup after writing configuration; task and operation history report the failure, changed content and original running intent. Unconfirmed writers block further applies; down and explicit recovery allow a versioned repair while preserving the stopped state and original failed history. This qualifies Docker lifecycle failure, not Minecraft readiness. |
| 重启计划与创建参数校验 | `servers.restart-schedule-and-creation` | 拒绝非法创建参数组合；创建服务器时一并建立重启计划；验证计划读取、更新、暂停、恢复、取消、稳定 ID、下次执行时间和自动默认值；删除服务器时取消计划。 |
| 重启计划逻辑目标 | `servers.restart-schedule-logical-target` | 并发受管创建只产生一个计划，显示名完全相同的独立任务不被接管。受管计划允许任意显示名，暂停、恢复和真实后端重启保留参数与分类。删除服务器精确取消活动受管与独立重启任务；显式恢复后真实调度对缺失目标记录带原因和终态元数据的 `skipped`。同名新实例保留暂停计划和原 ID，显式恢复后的执行定位当前停止实例并记录另一种跳过原因，不启动服务器。再次重启保留两次执行历史，独立任务仍可明确恢复。 |
| 历史重启计划迁移 | `servers.restart-schedule-legacy-migration` | 停止独占数据库并降级至 `2026092501` 后，以标准 SQLite 预置重复受管计划、早于服务器登记的计划、独立任务和真实历史表记录。启动至当前 schema 后保留原 ID、显示名、参数、cron、状态、执行次数和完整历史，活动计划正常注册，API 不再暴露旧绑定字段。服务器页面选最早未取消计划，逐项暂停、恢复和取消不影响其他记录，全部取消时选择最新取消项供明确恢复和更新；不新增替代 ID。删除服务器只取消参数精确匹配的活动任务，共同前缀另一服务器的计划和全部执行历史保持。 |
| 定时任务实际重启 Minecraft | `minecraft.scheduled-restart` | 建立真实的分钟级计划并检查下次执行时间；等待执行历史完成，确认 Docker 启动时间发生变化、服务器恢复健康；通过 RCON 验证白名单与记分板数值保留，并核对世界标记文件。 |
| 受管计划精确身份 | `minecraft.exact-restart-schedules` | 建立服务器名称前缀相似的计划及独立自定义 cron；验证 GET、更新、暂停、恢复、删除均只作用于精确归属的受管计划，其他任务保持原状。 |
| 文件系统与数据库同步 | `servers.sync-reconciliation` | 验证仅 owner 可同步、状态一致时的试运行、真实项目目录偏差及强制执行保护；停用与接管预览不修改状态；实际应用两种转换后核对服务器清单和状态。 |
| 显式服务器身份 | `minecraft.explicit-server-identity` | 孤立目录及接管预览均不允许写入；owner 显式接管后才可修改；缺失项目不能覆盖 ACTIVE 记录重建，停用后恢复目录不隐式激活；再次接管保留原文件，历史合法名称及登记在重启后仍可使用。实例代次与延迟任务复检由隔离的后端并发测试验证。 |
| 服务器路径归属 | `minecraft.server-path-boundaries` | 拒绝 dot/dot-dot 服务器名称；项目 symlink 别名、指向根目录的 data symlink 均不能读取或写入目标；修复链接后通过 API 核对原文件完整。配置根 symlink 及本项目内部 data symlink 的兼容性由后端路径测试验证。 |
| Minecraft 生命周期 | `minecraft.lifecycle` | 通过 API 保存含多个等号的合法标签值，实际创建并启动 Docker/Minecraft，等待应用返回健康状态；修改和读取 RCON 白名单，验证消息接口；拒绝删除运行中的服务器；停止后修改配置并重建，确认新配置生效且保持停止，再次启动达到健康状态；手动 up/start/restart/stop/down 均核对新增唯一成功操作历史、操作者、运行意图、结束阶段及同一服务器代次，最后删除服务器。 |
| 运行概览与配置 | `minecraft.overview`、`minecraft.rcon-and-files` | 验证统一监控中的受管服务器与有效资源样本、在线玩家、生成的世界布局、真实 RCON 输出及生成的 `server.properties`。 |
| 共享监控与实例重启 | `minecraft.shared-monitoring` | 并发观察保留同一服务器代次和采样身份；真实停服后运行指标明确不可用、维护已结束；重新启动后服务器代次不变、容器采样身份变化，恢复有效 CPU、内存、累计 I/O 与目录占用样本；下线后直接提交启动意图可重新创建容器并通过真实 RCON 验证。首次预热、部分故障、慢目录、同名代次替换及未知 writer 阻塞由后端定向测试覆盖。 |
| Docker 控制台与运行时修改 | `minecraft.console-and-runtime-controls` | 验证 CPU、内存、IO、磁盘计数，控制台历史、尺寸调整、输入和未知消息协议；通过标准输入执行修改，再用 RCON 核对效果；验证格式化消息、运行中填充服务器数据的冲突、停止与启动，以及运行中修改 Compose 内存限制后的重建效果。 |
| 控制台适配器错误安全输出 | `minecraft.console-safe-adapter-errors` | 在自有运行中 Minecraft 的 Compose 中设置 `logging.driver=none`，使真实 Docker SDK 无法读取历史；验证固定中文历史错误帧，同时 attach/stdin 仍可执行命令；通过 RCON 核对实际白名单变更，正常关闭 WebSocket 后服务器仍健康，普通容器日志不包含适配器原始 HTTP/文本诊断。 |
| 已停止、缺失与非法请求 | `minecraft.stopped-and-invalid-requests` | 验证已停止服务器的指标、RCON、消息冲突和控制台错误帧；拒绝非法命令、消息长度与字段、非法操作；检查不存在的服务器响应。 |
