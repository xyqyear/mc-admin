# 非快照后台操作

耗时管理操作由功能模块提交给 runtime 的 `BackgroundTaskManager`。HTTP 请求完成鉴权和必要的输入准备，提交 durable journal 后返回 `202 {task_id}`；worker 持有自己的会话、资源范围和清理责任。前后端同步部署，不保留旧执行接口。快照创建、恢复、回滚、预览及仓库维护由 [公共快照服务](snapshot-restoration.md) 单独拥有。

## 操作入口

| 操作 | 入口 / worker | 前端观察与完成行为 |
| --- | --- | --- |
| 启动、重启、停止、下线、删除服务器 | `/servers/{id}/operations`；`servers/tasks.py` | 保持按钮忙碌，展示当前原因和任务入口；命令完成后恢复操作，Minecraft 就绪状态单独查询 |
| 创建服务器 | `/servers/{id}`；`servers/tasks.py` | 完成创建后才执行填充、导航和原有成功提示 |
| 登记同步与预览 | `/servers/sync`；`servers/synchronization.py` | 任务结果包含预览、导入/停用数量和逐项错误；保留确认与 force 流程 |
| 文件、目录删除 | `DELETE /servers/{id}/files`；`files/application.py` | 单项/批量操作等到终态才计入成功或失败；不锁住无关路径 |
| 压缩包目录删除 | `DELETE /archive`；`archive/application.py` | 等待实际删除后更新列表 |
| 地图初始化、强制重载 | `/servers/{id}/map/initialize`；`mcmap/initialization.py` | 保留 client/palette 两阶段进度；真实终态前不允许关闭 |
| 全量、单项手动自检 | `/self-check/run`、`/self-check/checks/{id}/run`；`self_check/tasks.py` | 保留逐项发现和历史结果；检查完成但有警告仍是成功执行 |
| 手动 DNS/router 同步 | `/dns/update`；`dns/tasks.py` | 等待真实结果，失败也刷新各提供方状态；返回页面后恢复忙碌原因和任务入口 |
| 上传服务端 SHA256、发布 | `/archive/upload/{id}/sha256`、`/verify`；`archive/uploads.py` | 保留浏览器传输和本地摘要，验证/发布阶段等待任务状态；hash 完成不代表文件已发布 |
| 已有重建、填充、压缩、所有权修复、区块清理 | 原有 task API | 保持各自可关闭/不可关闭规则和取消能力，不叠加第二个任务 |

## 完成与页面观察

GET `/tasks/{id}` 提供当前阶段、进度、结果和安全错误。未知总工作量使用不定进度，不伪造 Docker 拉取百分比。202、100% 进度以及查询失败都不代表操作完成。`waitForTaskResult` 在 pending/running 和查询重试期间持续等待；只在 confirmed terminal 后调用原有处理。离开可导航页面只脱离观察；全局 observer 根据 journal 终态刷新业务查询，包括页面离开、短任务完成和部分失败。

## 实例与资源所有权

统一监控 `/api/monitoring` 中的服务器维护投影报告恢复保护、已接受生命周期任务、删除冻结或当前维护持有者的原因。只有实际任务才带 task_id；快照和定时维护仍可以展示原因。生命周期提交在任何 await 前预留互斥 key，同服务器冲突返回 423 和已有任务 ID。停止/下线允许处理恢复保护中的实例，但不能清除保护或绕过删除冻结。

现有服务器捕获不可变 ServerRef，执行和取得资源时核对 generation 与路径。创建先捕获配置，在目录/端口租约内写入，登记后把 prospective 范围绑定到新 generation。同步捕获完整的现有实例集合，允许缺失目录，并在逐项停用前重新核对；它使用自己的 DB 会话。删除排空其它任务，只排除自己的 operation ID。

## 取消、关闭与持久化

不能安全中断的 Docker 生命周期、创建、删除、登记同步、自检历史写入、DNS 和发布不展示取消按钮。地图初始化和哈希可以取消，必须等子进程、线程和输入清理完成。应用关闭仍排空所有 worker。重启将未完成工作记为中断，不自动重放；详细任务结果在 journal 保留期内跨关闭和重启保留，摘要查询不加载结果 payload；cron、恢复等功能历史仍独立存在。持久化和观察协议见 [后台任务](background-tasks.md) 与 [操作刷新](../../frontend-react/docs/operation-refresh.md)。

## 上传会话

上传会话的 HEAD 暴露 hash/publication 任务关联。活跃任务不会因 TTL 丢失输入；重复哈希和重复发布可以重新观察同一任务。发布成功后的 session 保留到 TTL，临时文件已删除。原浏览器 File 对象不能跨刷新恢复；重新选择文件与任务中心观察是不同责任。
