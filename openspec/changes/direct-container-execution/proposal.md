## Why

Query 和 RCON 的 Compose CLI 启动增加调用开销。直接使用 Docker API，并让容器自带的 timeout 管理命令期限，可以简化调用并补齐 RCON 的容器内超时。

## What Changes

- Query、RCON 和消息使用 Runtime 拥有的 Docker 命令适配器；Compose 保留生命周期操作。
- 同一次 exec 内以 command -v 优先选择 gnutimeout，不存在时选择 timeout；不验证实现或版本，不缓存，不因命令失败重发。
- Query 保留保存的限时；RCON 使用 8 秒执行限时和 1 秒强杀宽限，外层 10 秒覆盖排队、通信和结果等待。
- 接受 timeout 实现自身的检查延迟及标准进程组边界，不引入额外进程管理协议。
- 保留查询降级、消息顺序、权限和错误分类，执行日志不包含命令或原始错误输出。

## Capabilities

### New Capabilities

- `container-command-execution`：通过 Docker API 和镜像已有的限时工具执行查询和命令。

### Modified Capabilities

无。

## Impact

修改后端命令适配器、Runtime、MCInstance、RCON 路由及相关测试和文档。不新增配置、依赖、迁移、端点或字段，不修改快照/回档、pidfd、操作恢复及 Compose 生命周期。接受 Rust timeout 的约 100ms 延迟。线上部署另行授权。
