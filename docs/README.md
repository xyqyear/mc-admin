# MC Admin 文档

这里按任务提供当前文档入口。开发执行规则见 [AGENTS.md](../AGENTS.md)，
可观察行为的验收契约见 [OpenSpec specs](../openspec/specs/)。

## 开始工作

| 任务 | 阅读入口 |
| --- | --- |
| 安装依赖并启动开发环境 | [开发环境](development.md) |
| 了解 API、界面和测试的职责 | [后端索引](../backend/docs/README.md)、[前端索引](../frontend-react/docs/README.md)、[E2E 索引](../e2e/docs/README.md) |
| 选择本地测试并完成交付验证 | [交付要求](../AGENTS.md#交付与测试要求)、[CI](ci.md#validation) |
| 构建、验证或发布镜像 | [发布与候选制品](release.md) |
| 理解快照、恢复与升级边界 | [快照与恢复](snapshot-recovery.md) |
| 添加、拆分或维护文档 | [文档归属与维护](documentation.md) |

## 文档边界

- 根目录 `docs/` 解释跨组件流程、开发环境、CI 和部署。
- 组件 `docs/` 解释当前架构、模块机制及失败恢复；各自索引维护完整主题目录。
- `openspec/specs/` 保存行为契约；`openspec/changes/` 保存提案、任务和变更证据。
- 已归档方案用于追溯，当前行为与操作步骤通过本索引进入。
