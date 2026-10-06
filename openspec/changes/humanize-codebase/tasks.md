## 1. Behavior oracles and test boundaries

- [x] 1.1 RT-05: 并发测试验证同时进入和每任务独立结果; implement the reviewed scope and verify its business contract.
- [x] 1.2 RT-06: 只合并重复搭建，保留 receipt、类型和中间进度契约; implement the reviewed scope and verify its business contract.
- [x] 1.3 TC-04: 地图fanout验证坐标与取消后的幸存成功; implement the reviewed scope and verify its business contract.
- [x] 1.4 TC-05: 完整 argv 观测即可，不再造测试用 CLI parser; implement the reviewed scope and verify its business contract.
- [x] 1.5 TC-06: 子路径压缩验证实际成员与未选数据隔离; implement the reviewed scope and verify its business contract.
- [x] 1.6 TD-04: 并发玩家测试证明先创建再关闭; implement the reviewed scope and verify its business contract.
- [x] 1.7 TD-06: 皮肤 handoff 测试观察真实数据库结果; implement the reviewed scope and verify its business contract.
- [x] 1.8 DM-10: 真正触发 union guard，保留独立的项目边界; implement the reviewed scope and verify its business contract.
- [x] 1.9 TF-04: 补文件夹上传身份与实际 multipart 字节 oracle; implement the reviewed scope and verify its business contract.
- [x] 1.10 TF-05: 保留上传生命周期替身，补真实 hash 与发布等待 oracle; implement the reviewed scope and verify its business contract.
- [x] 1.11 TF-06: 退出测试触发真实清理路径，保留跨session隔离; implement the reviewed scope and verify its business contract.
- [x] 1.12 E2-01: 修复 E2E 配置与世界别名预期对象污染; implement the reviewed scope and verify its business contract.
- [x] 1.13 E2-02: 合并重复 full self-check，按创建ID验证历史; implement the reviewed scope and verify its business contract.
- [x] 1.14 E2-03: 过滤结果验证精确身份与数量一致; implement the reviewed scope and verify its business contract.
- [x] 1.15 E2-04: 统一当前候选的 task 等待循环; implement the reviewed scope and verify its business contract.
- [x] 1.16 E2-05: 只共享 multipart 编码，业务发送与断言留原suite; implement the reviewed scope and verify its business contract.
- [x] 1.17 E2-06: 仅合并现有固定压缩工作量；撤回无测量的暂停方案; implement the reviewed scope and verify its business contract.
- [x] 1.18 E2-07: 空文件 oracle 区分缺失/null与真实空内容; implement the reviewed scope and verify its business contract.
- [x] 1.19 CN-07: DNS 写测试必须检查实际外部 payload; implement the reviewed scope and verify its business contract.
- [x] 1.20 CN-08: 实际 cron 调度测试等待持久终态; implement the reviewed scope and verify its business contract.
- [x] 1.21 TD-05: 删除无断言 empty smoke，先补实际配置替换; implement the reviewed scope and verify its business contract.
- [x] 1.22 ST-08: 仅替换高层 ownership mock 顺序 oracle; implement the reviewed scope and verify its business contract.

## 2. Explicit correctness and error-output fixes

- [x] 2.1 TF-02: 独立修复 Cron 0/空串被旧闭包覆盖; implement the reviewed scope and verify its business contract.
- [x] 2.2 TF-03: 独立修复目录勾选完整集合丢更新; implement the reviewed scope and verify its business contract.
- [x] 2.3 FE-05: 区分 SSE 解析失败、handler 失败及玩家有限流终态; implement the reviewed scope and verify its business contract.
- [x] 2.4 ST-10: 上传错误公开原文必须作为独立修复; implement the reviewed scope and verify its business contract.
- [x] 2.5 CN-09: 独立修复 raw public/history/log 输出; implement the reviewed scope and verify its business contract.

## 3. Retire unused internal surfaces

- [x] 3.1 RT-01: 删除确认无消费者的内部入口与别名; implement the reviewed scope and verify its business contract.
- [x] 3.2 RT-07: 删除失实说明与机械叙述，保留语义说明; implement the reviewed scope and verify its business contract.
- [x] 3.3 ST-02: 删除确认无消费者的内部入口; implement the reviewed scope and verify its business contract.
- [x] 3.4 FE-02: 删除已全仓确认无消费的手写导出; implement the reviewed scope and verify its business contract.
- [x] 3.5 DM-02: 移除测试专用 Compose writer，迁移真实 Docker 效果覆盖; implement the reviewed scope and verify its business contract.
- [x] 3.6 DM-03: 移除三个测试专用聚合入口; implement the reviewed scope and verify its business contract.
- [x] 3.7 DM-04: 删除两个无业务消费者的配置便利 API; implement the reviewed scope and verify its business contract.
- [x] 3.8 DM-06: 按固定清单删除监控便利 API，保留 wire 和真实 source checks; implement the reviewed scope and verify its business contract.
- [x] 3.9 DM-07: 删除六个确认无消费者的旧别名和 exports; implement the reviewed scope and verify its business contract.
- [x] 3.10 DM-08: 移除任意名字 proxy，保留 typed owning view和generic manager; implement the reviewed scope and verify its business contract.
- [x] 3.11 CN-01: DNS 旧接口受控退役，保留现行 DTO; implement the reviewed scope and verify its business contract.
- [x] 3.12 CN-03: 删除无生产需求的排时查询和pattern参数; implement the reviewed scope and verify its business contract.
- [x] 3.13 CN-04: 先收窄 decorator 能力，安全日志另立项; implement the reviewed scope and verify its business contract.
- [x] 3.14 CN-05: 只保留显式 cron 注册入口; implement the reviewed scope and verify its business contract.
- [x] 3.15 CN-06: 删除确实未使用的供应商锁与操作映射; implement the reviewed scope and verify its business contract.

## 4. Equivalent concrete helpers and measured costs

- [x] 4.1 ST-01: 共用玩家所属的 UUID 语法规范化; implement the reviewed scope and verify its business contract.
- [x] 4.2 ST-05: 上传覆盖策略只解释一次; implement the reviewed scope and verify its business contract.
- [x] 4.3 ST-06: 归档使用已有 canonical confinement helper; implement the reviewed scope and verify its business contract.
- [x] 4.4 DM-01: 统一 finding 存储解码，查询形状保持; implement the reviewed scope and verify its business contract.
- [x] 4.5 DM-09: 路由复用现有 user_to_public，原 guard保留; implement the reviewed scope and verify its business contract.
- [x] 4.6 CN-02: 统一 planner record 类型时显式迁移字段顺序; implement the reviewed scope and verify its business contract.
- [x] 4.7 FE-03: 统一玩家身份的 UUID 纯规范化函数; implement the reviewed scope and verify its business contract.
- [x] 4.8 FE-04: 复用同一 Minecraft→Leaflet 坐标 helper; implement the reviewed scope and verify its business contract.
- [x] 4.9 FE-08: 精简 Cron 参数表单 API，保留实际 renderer 策略; implement the reviewed scope and verify its business contract.
- [x] 4.10 FE-10: 缩小 FileIcon 输入，删除伪造 metadata 适配; implement the reviewed scope and verify its business contract.
- [x] 4.11 ST-09: Process 缓存需要独立生命周期方案; implement the reviewed scope and verify its business contract.
- [x] 4.12 CI-01: OCI layer流式校验属于perf候选，未证实OOM; implement the reviewed scope and verify its business contract.
- [x] 4.13 CI-02: 用标准深复制代替 JSON 往返; implement the reviewed scope and verify its business contract.

## 5. Structural simplification with preserved lifecycle

- [x] 5.1 RT-02: 固定类型的惰性运行时归属，显式关闭当前资源; implement the reviewed scope and verify its business contract.
- [x] 5.2 RT-03: 任务 summary 统一字段，detail 只增加 result; implement the reviewed scope and verify its business contract.
- [x] 5.3 RT-04: 共用有限数据库工作的取消传播协议; implement the reviewed scope and verify its business contract.
- [x] 5.4 RT-08: 共享登记与释放 lease 的具体生命周期; implement the reviewed scope and verify its business contract.
- [x] 5.5 RT-09: 共用状态纯投影和 terminal dismissal; implement the reviewed scope and verify its business contract.
- [x] 5.6 ST-03: 公共 typed chunk 操作取代跨类私有调用; implement the reviewed scope and verify its business contract.
- [x] 5.7 ST-04: 渲染队列声明真实双 cache 接口; implement the reviewed scope and verify its business contract.
- [x] 5.8 FE-01: 将二级 hooks 工厂迁移为具体命名 hooks; implement the reviewed scope and verify its business contract.
- [x] 5.9 FE-06: 先修 Cron 值错误，再类型化局部编辑状态; implement the reviewed scope and verify its business contract.
- [x] 5.10 FE-07: 复用地图页面的具体展示接线，保留业务组件寿命; implement the reviewed scope and verify its business contract.
- [x] 5.11 FE-09: 共享最小路径树构造，保留三种树的交互差异; implement the reviewed scope and verify its business contract.

## 6. Convergence and delivery

- [x] 6.1 Synchronize current-state docs, AGENTS.md, behavior specs and API E2E coverage.
- [x] 6.2 Complete independent implementation review and fix cycles until stable.
- [x] 6.3 Run affected targeted tests and required backend/frontend/Go static and build checks.
- [ ] 6.4 Commit atomic changes, push the branch and qualify every required gate for the latest SHA with publish=false.
- [ ] 6.5 Record finding dispositions, validation evidence, line delta, commit SHA and qualification link.
