# 统一快照恢复：交付验证

开发分支为 `feat/unify-snapshot-recovery`。本记录区分已经通过的实现批次、部署演练和最终分支资格；完成的设计与任务清单保存在 `openspec/changes/archive/2026-10-06-unify-snapshot-recovery/`，发布镜像需用户授权。

## 完整 CI

每批均运行 `Qualify and Publish Application`，`publish=false`。验证包括 candidate/Go、后端与前端静态检查、四个后端分片及覆盖审计、三个 API 分片及覆盖审计、真实浏览器流程和最终 qualification。API 子流程中的独立 build 不使用，因为它消费同次 candidate 产物；发布步骤按参数跳过。

| 批次 | 提交 | 完整 Actions |
| --- | --- | --- |
| 范围、保护、历史与迁移基础 | `974a44` | [36680174034](https://github.com/xyqyear/mc-admin/actions/runs/36680174034) |
| 手动创建与文件恢复 | `ff39c4f` | [36686670190](https://github.com/xyqyear/mc-admin/actions/runs/36686670190) |
| 世界执行与精确缓存清理 | `4f31e77` | [36694438860](https://github.com/xyqyear/mc-admin/actions/runs/36694438860) |
| 共用预览、仓库维护与子进程取消 | `d57b44a75404908049e157026232dab8391a593b` | [36705471988](https://github.com/xyqyear/mc-admin/actions/runs/36705471988) |
| 刷新观察、忽略反馈及删除/收尾保护 | `3015abcdfba1f806dd8eff613011056ae373eb6c` | [36711350144](https://github.com/xyqyear/mc-admin/actions/runs/36711350144)，通过 |
| 最终结构、迁移演练脚本、文档及主规范 | `5c2fe8dcc44989ca9eec2fe1af8b09cc0119219a` | [36713825591](https://github.com/xyqyear/mc-admin/actions/runs/36713825591)，通过 |

最终实现提交为 `5c2fe8dcc44989ca9eec2fe1af8b09cc0119219a`，[资格证明](evidence/snapshot-recovery-qualification.json) 保存原始 candidate 标识和五类门槛结果。后续验收记录提交同样必须通过完整 CI；其最新 SHA 与 Actions 链接在交付报告中确认，不用上述实现提交的绿灯替代。

## 本地业务验证

- 真实 Restic/mcmap 验证文件及世界各选区、忽略保护并集、缺失状态、安全快照、重复回滚和缓存副作用；成功、失败、显式取消及进程恢复分别断言实际数据。
- 阶段六后端回归共 56 个用例通过；另有世界恢复/删除 27 个用例、收尾与删除专项 7 个用例、预览删除专项 4 个用例通过。它们包含重复覆盖，不作为唯一用例总数相加。
- 前端 34 个测试文件、168 个测试及 4 个架构测试通过；覆盖受理未完成、失败读取、无选区刷新恢复观察、完成结果保留和相同 MCA mtime 的瓦片刷新。
- 实际镜像 API 用例 `snapshots.restore-and-protection` 通过；真实浏览器文件与地图流程验证创建、恢复、刷新观察、历史回滚、忽略禁用及数据结果。完整 CI 再执行全部浏览器流程。
- Ruff、Pyright、前端 lint/类型、Go vet/race、HTTP 契约与 OpenSpec 严格校验通过。最终清理后再次执行前端全套测试、类型及边界检查，演练检查点单元测试和脚本 Ruff 通过。

## 真实发布版升级与配套回退

[机器可读结果](evidence/snapshot-recovery-deployment.json) 来自隔离的 owned Docker fixture，脚本为 `e2e/scripts/deployment_rehearsal.py`，SHA-256 为 `6fd6e2edac27300b70e6f13ce47c3223c058c8462d397487a2ade80e90036f17`。388 次公共 API 请求核对业务结果；测试容器、网络和持久目录已由其拥有者清理。

- 历史应用来自真实 `v6.0.0-beta.1`，Docker image ID 为 `sha256:1ca2c941ec72184a25c4d61a76a47f18cc9e40d79312c539cf3d11afc3633e1d`。使用该版本自己的 Go runner 建立数据；没有把新代码伪装成旧 schema。
- 候选来自 Actions `36711350144` 的原始 OCI 归档，源提交 `3015abcdfba1f806dd8eff613011056ae373eb6c`；manifest 为 `sha256:ac6fb202db0c16df444cb4b22f5de1efa45d7bf9a2d1a6b9e69c47c485f37c2f`，Docker config/image ID 为 `sha256:e18956517cb7008828b2300184e32bec081d8b7e167befb4bc7a2b13a8412b8d`。
- schema 从 `2026092503` 升至 `2026093000`。原用户、服务器、玩家历史、模板、暂停计划、配置、文件、压缩包及仓库快照仍可读取；仓库未重建。
- 旧版本通过真实恢复接口产生历史和安全快照。升级后原 ID、scope、generation 和安全引用保留；回滚及再次回滚均核对实际文件内容。停机时从真实旧记录派生的歧义身份样本保持可见，回滚返回 409，文件内容不变。
- 旧代码在完整升级副本上启动因未知 Alembic revision 被拒绝，前后所有表行摘要和持久文件摘要一致。原发布版在完整配套检查点上可启动；检查点后的数据在该恢复点不存在，独立升级副本仍完整保留。
- 已记录的同 schema 镜像 `sha256:6039066f225941c63a2a5319ba9c62fd07159cb0911fbcc88839514b7e5dbc1c` 能保留升级后数据。此结果只证明该具体镜像，不证明任意旧代码兼容。
- 再换回候选执行世界恢复和安全回滚，世界内容按目标变化，升级后普通文件、用户、cron 和玩家历史保持。

## 部署限制

前后端同镜像部署，不保留旧快照同步/SSE 执行 API。升级前停止接收任务并排空写入，保留数据库、服务器目录和仓库的配套恢复点。schema `2026093000` 在仍有恢复历史时拒绝降级；不能靠删除历史绕过保护。

完整检查点是回到检查点时刻的灾备，不会合并后续修改。未知写入者、身份歧义和未解决恢复引用不能因换镜像而忽略。历史快照允许正常保留策略回收，回收后统一历史会说明回滚不可用。外部服务资格与任意外部文件写入不在本轮普通 CI 的承诺范围内。
