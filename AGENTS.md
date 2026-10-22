# MC Admin

Minecraft server administration through Docker Compose. One application image
contains the FastAPI backend and built React frontend; the Go API E2E runner is
built independently.

| Working area | Instructions | Documentation |
| --- | --- | --- |
| `backend/` — Python, FastAPI, SQLAlchemy | [Backend rules](backend/AGENTS.md) | [Backend topics](backend/docs/README.md) |
| `frontend-react/` — React, TypeScript, TanStack Query | [Frontend rules](frontend-react/AGENTS.md) | [Frontend topics](frontend-react/docs/README.md) |
| `e2e/` — deployed API scenarios and owned environments | [E2E rules](e2e/AGENTS.md) | [E2E topics](e2e/docs/README.md) |

Read the applicable component instructions before editing that component. Use the
[documentation index](docs/README.md) to select the topics needed for the task.
Environment setup and binary prerequisites belong to [development](docs/development.md).

## 设计原则

- 前后端始终一起发布，不支持混合版本。API（含 HTTP、WebSocket、SSE）只面向当前版本设计；变更时同步更新契约、调用方和测试，不保留旧接口、旧字段或兼容分支。优先保证当前 API 清晰、一致、简洁；持久化数据的迁移与恢复保障仍须保留。
- 遵循 Keep It Simple、You Aren’t Gonna Need It 和 Avoid Premature Abstraction：只解决当前明确需求，不为假设的未来需求增加抽象、配置或重复逻辑。
- 遵循 Locality of Behavior 和 Boy Scout Rule：相关行为就近组织，修改时顺手清理涉及范围内的重复、死代码和过时设计，避免无关的大范围重构。

## 交付与测试要求

- 本地只运行改动直接相关及受影响调用路径的定向测试，必须用明确的文件、节点、包或用例筛选限定范围。禁止运行完整项目或任一组件的全量测试，也不得通过目录、分片或多个 agent 累计执行全量。必要的 lint、类型检查和构建仍按组件要求执行；纯文档变更不运行本地测试。
- 项目变更优先使用独立分支。完成本地定向验证后，必须 commit、push，再对最新提交运行完整 GitHub Actions；仅修改 Markdown 文件时不运行本地测试或 CI。其他变更不能以本地通过、部分检查通过或旧 SHA 的绿灯代表交付完成。
- 完整验证必须手动触发 `Qualify and Publish Application`（`.github/workflows/docker-image.yml`），选择开发分支并设置 `publish=false`。普通 push 检查不能替代完整验证。
- 执行完整 CI 前阅读 [CI 验证流程](docs/ci.md#validation)。确认最新 SHA 对应的 run ID 后，由主 agent 启动一次 `gh run watch <run-id> --exit-status --interval 60 --compact > <log-path> 2>&1`。等待期间静默，不读日志或进度、不开展其他工作；所有 agent 不得另行轮询同一 run/job。工具分段返回时继续等待同一命令。用户新消息可以中断等待；命令中断或连接失败不代表 CI 结束或通过。
- 等待命令退出后统一核对一次 SHA、最终结论、candidate/Go、static/frontend、全部 backend 分片及覆盖审计、全部 API E2E 分片及覆盖与清理审计、全部 browser 分片及覆盖审计和最终 qualification。失败后读取失败步骤，修复、定向验证、提交推送，再完整验证新 SHA；不得跳过检查、降低业务断言或用局部重跑代替。报告须附 SHA 和 Actions 链接；尚未通过时明确说明。
- 功能变化必须配套行为测试，从用户场景、输入输出、副作用、权限、失败与恢复边界验证。不得机械复刻实现；删除旧测试须有行为移除、契约替换或有效覆盖合并的依据。
- 同步/流式执行迁移到后台任务时，测试和 fixture 必须等待真实终态后验证结果，并覆盖受理不等于完成、重复提交、断线观察、取消/关闭和资源清理，保留独立的业务不变量断言。

## Cross-component rules

- User-facing application text is Chinese, including backend errors, names and descriptions.
- Use `uv` for Python and `pnpm` for Node. Use Context7 to resolve and query current library/API documentation; use IDE diagnostics for code issues when that tool is available.
- Observable backend behavior changes require API E2E coverage in `e2e/suites/` and an update to [the coverage inventory](e2e/docs/coverage.md), including its affected domain page, in the same change.
- Keep frontend generated shadcn sources under official CLI management. Do not hand-edit, move, delete or reformat them; the [frontend rules](frontend-react/AGENTS.md#generated-ui) define protected paths and commands. These sources are excluded from repository-wide cleanup.
- Do not hand-edit generated `.agents/skills/openspec-*` skills. Upgrade/regenerate them with the OpenSpec CLI. Repository-specific skills, including `gen-version-message`, live alongside them.
- [OpenSpec specifications](openspec/specs/) own observable behavior. Active changes contain proposals and implementation plans; completed changes retain their evidence under `openspec/changes/archive/` after specification sync. Keep current implementation rationale in component docs.
- Never log credentials or raw protocol frames containing login tickets. Production Uvicorn uses INFO; protocol DEBUG can expose even abbreviated tickets.

## Documentation maintenance

Follow [documentation ownership and maintenance](docs/documentation.md) when changing docs.
Update the owning topic when its behavior, implementation or workflow changes.
Update AGENTS.md only when agent instructions, commands, component boundaries or
reading routes change. Function signatures, hook/store details, schema revisions
and feature inventories belong in their topic documents or source.

Keep current-state descriptions and remove superseded claims. Preserve necessary
persisted-data migration and recovery boundaries, but keep change history in Git/OpenSpec
archives. Link to one detailed owner instead of copying its explanation. Add or
adjust the component documentation index whenever a topic is created or moved.
