# API E2E 文档

[运行入口](../README.md)提供构建、定向执行和清理命令；
[E2E 规则](../AGENTS.md)约束用例隔离、断言与资源所有权。

| 任务 | 文档 |
| --- | --- |
| 添加用例、环境 recipe 或 provider | [架构与扩展](architecture.md) |
| 查找某项业务的场景与覆盖边界 | [覆盖索引](coverage.md)及其领域清单 |
| 调整调度、分片、历史耗时或审计 | [调度与测量](scheduling.md) |
| 验证发布版升级、检查点与回退 | [部署演练](deployment-rehearsal.md) |
| 使用真实 DNS 服务及回收资源 | [DNS suite](../suites/dns/README.md) |
| 世界数据 fixture、恢复和进程中断 | [World suite](../suites/world/README.md) |
| 添加真实浏览器用例 | [浏览器验证](../../frontend-react/docs/browser-tests.md) |
| 完成远端 qualification 或发布 | [CI](../../docs/ci.md)、[发布](../../docs/release.md) |

文档调整遵循[文档归属与维护](../../docs/documentation.md)。
