# MC Admin 前端

使用 React 19、TypeScript、Vite 8、TanStack Query 和基于 Base UI 的 shadcn 组件。应用管理 Minecraft 服务器、文件、快照恢复、地图、玩家和定时任务。

需要 Node.js 24 和 pnpm；后端开发服务默认监听 `http://localhost:5678`。

```bash
pnpm install --frozen-lockfile
pnpm dev
```

开发页面位于 `http://localhost:3000`，Vite 将 `/api` 的 HTTP 和 WebSocket 请求代理到后端。生产构建由根目录 Dockerfile 打包，后端提供静态页面。

```bash
pnpm lint
pnpm typecheck
pnpm build:bundle
```

`src/app/` 组合路由布局、概览和全局操作观察；`src/features/` 拥有各业务的数据契约、查询、命令及界面；`src/shared/` 提供通用传输、UI、编辑器和工具；`src/pages/` 是服务器路由适配层；`browser/` 用真实部署环境验证浏览器流程。

密码和动态码登录均由后端建立 HttpOnly Cookie 会话，写请求携带 CSRF 令牌；客户端读取当前会话作为路由守卫依据。

开发约束和定向验证方式见 [AGENTS.md](AGENTS.md)，业务边界见 [数据架构](docs/data-architecture.md)，浏览器环境与观测方法见 [浏览器验证](docs/browser-tests.md)。本地仅运行与改动直接相关的测试文件或用例，完整验证由 GitHub Actions 执行。
