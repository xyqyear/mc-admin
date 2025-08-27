# MC Admin Frontend – Repository Instructions for Copilot

These instructions are sent with every chat in this repository. Read and trust this file first; only search the codebase if something here is missing or incorrect. If you add new tech, change structure, or introduce new workflows, update this file in the same pull request.

## What this repo is
- A React 18 + TypeScript single-page app that provides a web UI for administering Minecraft servers ("MC Admin").
- Built with Vite 5, Ant Design 5 for UI, and Tailwind CSS for utility styling (Tailwind preflight is disabled to avoid conflicts with AntD).
- State is handled via Zustand (with localStorage persistence). Data fetching/caching uses TanStack React Query + Axios with a sophisticated query architecture. Routing is React Router v6. Error handling uses react-error-boundary.

## Tech stack and libraries
- Runtime/Language: Node.js (>= 18 recommended), TypeScript 5
- Build tool: Vite 5 with @vitejs/plugin-react; path alias `@ -> src/`
- UI: Ant Design 5 (`antd`, `@ant-design/icons`)
- UI (extended): `@ant-design/pro-components` is available if you need advanced Ant Design Pro UI primitives
- Styles: Tailwind CSS 3 + PostCSS (autoprefixer). Tailwind preflight disabled in `tailwind.config.js` to prevent CSS resets conflicting with AntD
- Code Editor: Monaco Editor via `@monaco-editor/react` + `monaco-yaml` for YAML support and schema validation
- State: `zustand` (+ persist middleware)
- Data: `axios` + `@tanstack/react-query` (+ devtools)
- Routing: `react-router-dom@6`
- Error handling: `react-error-boundary`
- Code quality: ESLint (TypeScript + React hooks plugins), strict TS compiler options

Monaco Editor Configuration:
- Web workers configured in `main.tsx` for JavaScript, TypeScript, JSON, CSS, HTML, and YAML
- Custom YAML worker (`yaml.worker.js`) provides YAML language support
- Docker Compose schema validation enabled for intelligent autocompletion

When you need external library docs, use Context7 documentation retrieval: first resolve the library ID, then fetch focused docs (e.g., hooks/routing/theme). Prefer official docs via Context7 over web search.

## Build, run, and validate
Always ensure Node 18+ and install dependencies before running anything.

- Install deps (prefer pnpm if available, pnpm-lock.yaml is present):
  - pnpm: `pnpm install`

- Build (type-check + bundle):
  - pnpm: `pnpm build`
  - Script runs `tsc && vite build`. Treat any TS error as a blocker.

- Lint:
  - pnpm: `pnpm lint`
  - Uses ESLint with TypeScript parser and React plugins. Add a project ESLint config if you introduce new rules.

Assume a development server is already running. Don't try to start another one.

Environment configuration:
- API base URL is read from `import.meta.env.VITE_API_BASE_URL`. You can set it via `.env` files (e.g., `.env.local`) or your shell. Default fallback is `http://localhost:5678/api` in `src/utils/api.ts`.
- The login code WebSocket endpoint derives from the API base URL and connects to `${BASE_WS}/auth/code` (http -> ws, https -> wss).

## Project layout (paths are relative to repo root)
- `index.html` – Vite entry HTML
- `vite.config.ts` – Vite config (react plugin, alias `@`, dev port 3000)
- `tsconfig.json` – strict TS options, path mapping `@/* -> src/*`
- `tailwind.config.js`, `postcss.config.cjs` – Tailwind + PostCSS configuration
- `public/` – static assets. DO NOT TRY TO READ compose-spec.json. It's HUGE.
- `src/`
  - `main.tsx` – app bootstrap: React Query provider, AntD theme, Router, Monaco Editor worker configuration
  - `yaml.worker.js` – Monaco Editor YAML language worker for syntax highlighting and validation
  - `App.tsx` – routes, error boundary, protected/auth route wrappers
  - `components/`
    - `layout/` – `AppHeader`, `AppSidebar`, `MainLayout`, `ErrorFallback`, `LoadingSpinner`
    - `overview/` – `MetricCard`, `ServerStateTag`
    - `editors/` – Monaco Editor components: `ComposeYamlEditor`, `SimpleEditor`, `MonacoDiffEditor`
  - `hooks/` – authentication hooks: `useLoginApi`, `useCodeLoginApi` (WebSocket login)
    - `api/` – API layer: `serverApi.ts` (Axios-based API functions)
    - `queries/` – React Query hooks: `useServerQueries`, `useServerDetailQueries`, `useServerPageQueries`
    - `mutations/` – React Query mutations: `useServerMutations`
  - `pages/` – `Home`, `Login`, `Overview`, `Backups`, `server/*` (detail pages including compose.tsx, players.tsx, etc.)
  - `stores/` – Zustand stores: token (`mc-admin-token`), sidebar (`mc-admin-sidebar`), login preference (`mc-admin-login-preference`)
  - `types/` – shared types (e.g., `Server.ts`, `ServerInfo.ts`, `ServerRuntime.ts`)
  - `utils/api.ts` – Axios instance, interceptors, `queryKeys`
  - `index.css` – Tailwind directives and base sizing

## Architectural notes and conventions
- Imports should use `@/` alias for anything under `src/`.
- Authentication: `useTokenStore` persists JWT token. 401 responses clear the token via response interceptor; routes gate on token presence.
- Data fetching: Uses a sophisticated three-layer React Query architecture:
  - **API Layer** (`hooks/api/`): Raw Axios-based API functions (e.g., `serverApi.getServerInfo`)
  - **Query Layer** (`hooks/queries/`): React Query hooks with intelligent caching, refetch intervals, and dependencies (e.g., `useServerQueries`)
  - **Composed Queries** (`hooks/queries/useServerDetailQueries.ts`): Page-specific hooks that combine multiple queries with smart invalidation
  - Prefer the composed query hooks for pages; use stable keys from `utils/api.ts::queryKeys`
- Mutations: Use `hooks/mutations/useServerMutations.ts` for server operations with optimistic updates and cache invalidation
- UI: Follow Ant Design v5 patterns. Tailwind utility classes are used sparingly for layout; avoid enabling Tailwind preflight.
- Routing: React Router v6 with nested routes and `Outlet` (see `App.tsx`).
- Error handling: Wrap risky views in `react-error-boundary`; use AntD `App` notifications for user-facing errors.
- Code Editing: Three specialized Monaco Editor components available:
  - `ComposeYamlEditor`: Docker Compose YAML files with schema validation and autocompletion
  - `SimpleEditor`: General-purpose code editor for various file types
  - `MonacoDiffEditor`: Side-by-side diff comparison with syntax highlighting
- Local State Management: Browser localStorage is used for draft configurations (e.g., compose.tsx unsaved changes) with intelligent consistency checking against server state

## What to do when you make changes (maintenance rules)
- If you introduce new libraries, frameworks, build steps, scripts, env vars, or change structure/routes, update this file to keep future sessions accurate.
- Document any new npm/pnpm scripts and when to run them. If you add tests or CI, include precise run/build/validate steps here.
- Keep the dev server port and env var usage in sync with config.

## For Copilot (new sessions): how to work effectively here
- Read and trust this file. Use its build/run steps first; only search if something is missing or failing.
- Trusting this file means if you add tech/features or restructure, you HAVE TO update this file in your PR so the guidance stays current. Don't update this file everytime, only when you feel future sessions will benefit from it.
- Use Context7 to look up external library docs (Ant Design, React Query, React Router, Zustand, Vite, Tailwind, Monaco Editor): resolve the library ID, then fetch the relevant docs topic before coding against unfamiliar APIs.
- Prefer `@` path alias imports. Use `queryKeys` for cache consistency. Do not enable Tailwind preflight.
- Data fetching patterns:
  - For pages, use composed query hooks from `hooks/queries/useServerDetailQueries.ts` or `useServerPageQueries.ts`
  - For new queries, add them to `hooks/queries/useServerQueries.ts` first, then compose them if needed
  - For mutations, extend `hooks/mutations/useServerMutations.ts`
  - API functions go in `hooks/api/serverApi.ts`
- Monaco Editor: Use the pre-built editor components in `components/editors/` rather than importing Monaco directly. Web workers are already configured.
- Local state: For draft configurations, use localStorage with consistency checking patterns (see compose.tsx as reference)
- Validate with: install -> build -> lint. Treat TS errors as blockers.
