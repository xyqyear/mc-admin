# MC Admin Frontend - React Development Guide

## What This Component Is

Modern React 18 + TypeScript single-page application providing the web UI for MC Admin Minecraft server management. Features a responsive interface with real-time updates, sophisticated data management, and integrated code editing capabilities.

## Tech Stack

- **Runtime**: Node.js 18+ with pnpm package management (pnpm-lock.yaml present)
- **Framework**: React 18 + TypeScript 5 with strict compiler options
- **Build Tool**: Vite 5 with @vitejs/plugin-react, path alias `@` → `src/`, dev port 3000
- **UI Framework**: Ant Design 5 (`antd` v5.13.3, `@ant-design/icons`, `@ant-design/pro-components`)
- **Styling**: Tailwind CSS 3 + PostCSS + autoprefixer (preflight disabled for AntD compatibility)
- **State Management**: Zustand v4.5.0 with localStorage persistence middleware
- **Data Fetching**: TanStack React Query v5.85.5 + Axios with sophisticated caching and retry strategies
- **Code Editor**: Monaco Editor v0.52.2 + monaco-yaml v5.4.0 with Docker Compose schema validation
- **Routing**: React Router v6.21.3 with nested routes and future flags enabled
- **Error Handling**: react-error-boundary v6.0.0 for graceful error boundaries

## Development Commands

### Environment Setup
```bash
pnpm install    # Install dependencies (preferred - pnpm-lock.yaml present)
# Alternative: npm install (fallback)
```

### Build and Quality
```bash
pnpm build      # TypeScript check + Vite bundle (tsc && vite build) 
pnpm lint       # ESLint with TypeScript and React plugins
pnpm preview    # Preview production build
```

**Note**: Development server is typically already running. Check before starting another instance.

### Environment Configuration
```bash
# Create .env.local for local development overrides
VITE_API_BASE_URL=http://localhost:5678/api  # Backend API endpoint
```

- **API Base URL**: Configurable via `VITE_API_BASE_URL` environment variable
- **Default**: `http://localhost:5678/api` (defined in `src/utils/api.ts`)
- **WebSocket**: Automatically derives from HTTP base URL (`ws://` or `wss://`)

## Architecture Overview

### Project Structure
```
src/
├── main.tsx                 # App bootstrap: providers, theme, Monaco workers
├── App.tsx                  # Routes, error boundaries, auth wrappers
├── yaml.worker.js           # Monaco Editor YAML language worker
├── components/
│   ├── layout/              # AppHeader, AppSidebar, MainLayout, ErrorFallback, LoadingSpinner
│   ├── overview/            # Metric cards: SimpleMetricCard, ProgressMetricCard, ServerStateTag  
│   └── editors/             # Monaco editors: ComposeYamlEditor, SimpleEditor, MonacoDiffEditor
├── hooks/
│   ├── api/serverApi.ts     # Raw Axios-based API functions
│   ├── queries/             # React Query hooks: useServerQueries, useServerDetailQueries, useServerPageQueries
│   └── mutations/           # React Query mutations: useServerMutations
├── pages/                   # Route components including Overview, Login, server/[id]/* detail pages  
├── stores/                  # Zustand stores: token, sidebar state, login preferences
├── types/                   # TypeScript definitions: Server, ServerInfo, ServerRuntime
├── utils/api.ts             # Axios instance, interceptors, stable queryKeys
└── index.css                # Tailwind directives and base styles
```

### Data Architecture (Three-Layer System)

**1. API Layer** (`hooks/api/serverApi.ts`):
- Raw Axios functions (e.g., `serverApi.getServerInfo`, `systemApi.getSystemInfo`)
- HTTP client configuration with interceptors
- Error handling and response transformation

**2. Query Layer** (`hooks/queries/`):
- React Query hooks with intelligent caching strategies  
- Different refetch intervals based on data volatility:
  - Server configs: 5min stale time (rarely change)
  - Server status: 10s refetch interval (frequent updates)
  - Server runtime: 5s refetch interval (real-time monitoring)
- Automatic error retry with smart 4xx handling

**3. Composed Queries** (`hooks/queries/useServerDetailQueries.ts`, `useServerPageQueries.ts`):
- Page-specific hooks combining multiple queries
- Intelligent dependency management (status → runtime queries)
- Centralized data management for complex pages

### Authentication & State

**Authentication:**
- JWT tokens stored in Zustand with localStorage persistence (`mc-admin-token`)
- Automatic token clearing on 401 responses via Axios interceptor
- Protected routes with authentication guards

**Global State (Zustand Stores):**
- **Token Store**: JWT authentication state
- **Sidebar Store**: UI layout preferences (`mc-admin-sidebar`)
- **Login Store**: Login method preferences (`mc-admin-login-preference`)

**Local State Patterns:**
- Draft configurations in localStorage (e.g., compose.tsx unsaved changes)
- Consistency checking between local drafts and server state
- Real-time validation and conflict detection

### Monaco Editor Integration

**Web Workers Configuration:**
- Pre-configured workers for JS, TS, JSON, CSS, HTML, YAML
- Custom YAML worker (`yaml.worker.js`) with Docker Compose schema support
- Workers initialized in `main.tsx` with `MonacoEnvironment`

**Editor Components:**
- **ComposeYamlEditor**: Docker Compose files with schema validation and autocompletion
- **SimpleEditor**: General-purpose code editor for various file types  
- **MonacoDiffEditor**: Side-by-side diff comparison with syntax highlighting

**Features:**
- Docker Compose schema validation for intelligent autocompletion
- YAML syntax highlighting and error detection
- Configurable themes and editor options

## Development Patterns

### Import Conventions
```typescript
// Always use @ alias for src/ imports
import { serverApi } from '@/hooks/api/serverApi'
import { useServerQueries } from '@/hooks/queries/useServerQueries'
import { queryKeys } from '@/utils/api'
```

### Data Fetching Best Practices
```typescript
// For pages: use composed query hooks
const { serverInfo, isLoading } = useServerDetailData()

// For new queries: add to useServerQueries first
const useServerLogs = (id: string) => useQuery({
  queryKey: queryKeys.serverLogs.detail(id),
  queryFn: () => serverApi.getServerLogs(id),
  // ... configuration
})

// For mutations: extend useServerMutations
const { useServerOperation } = useServerMutations()
```

### UI Development Guidelines
- **Ant Design First**: Use AntD components as primary UI building blocks
- **Tailwind Utilities**: Use only for spacing, layout, and minor adjustments
- **Never Enable Tailwind Preflight**: Disabled in `tailwind.config.js` to avoid AntD conflicts
- **Error Boundaries**: Wrap risky components with `react-error-boundary`
- **Notifications**: Use AntD `App` component notifications for user feedback

### Local State Management
```typescript
// Draft configuration pattern (see compose.tsx)
const [localConfig, setLocalConfig] = useState('')
const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)

// Save to localStorage with consistency checking
const handleSaveLocal = () => {
  localStorage.setItem(`compose-${id}`, localConfig)
  setCheckTrigger(prev => prev + 1) // Trigger consistency check
}
```

## React Query Configuration

**Global Defaults** (configured in `main.tsx`):
- **Stale Time**: 5 minutes default
- **Retry Strategy**: Smart 4xx handling (don't retry except 408, 429)  
- **Window Focus**: Refetch disabled
- **GC Time**: Automatic cleanup
- **Mutations**: No retry by default

**Query Key Structure** (from `utils/api.ts`):
```typescript
export const queryKeys = {
  serverInfos: {
    lists: () => ['serverInfos'],
    detail: (id: string) => ['serverInfos', id]
  },
  serverStatuses: {
    detail: (id: string) => ['serverStatuses', id]
  }
  // ... stable, hierarchical structure
}
```

## External Documentation

**Always use Context7 for external library documentation:**
- **Ant Design**: `/ant-design/ant-design`
- **React**: `/facebook/react`
- **TanStack Query**: `/tanstack/query`  
- **React Router**: `/remix-run/react-router`
- **Zustand**: `/pmndrs/zustand`
- **Vite**: `/vitejs/vite`
- **Monaco Editor**: `/microsoft/monaco-editor`
- **Tailwind CSS**: `/tailwindlabs/tailwindcss`

**Process**: 
1. Use `mcp__context7__resolve-library-id` to find the correct library ID
2. Use `mcp__context7__get-library-docs` with specific topics (hooks, theming, etc.)

## Integration Notes

- **Backend API**: Connects to FastAPI backend at configurable base URL
- **WebSocket**: Auto-derived from HTTP base URL for real-time features
- **CORS**: Backend configured for localhost:3000 development
- **Build Output**: Static files served by Vite with optimized bundling
- **Future React Router**: Prepared for v7 with future flags enabled

## Update Instructions

When adding new features, libraries, or changing architecture:

1. **New dependencies**: Update `package.json` and document major additions here
2. **New routes**: Add to `App.tsx` and update routing patterns
3. **New API endpoints**: Add to `hooks/api/serverApi.ts` first
4. **New queries**: Extend query hooks in `hooks/queries/` 
5. **New state**: Consider Zustand stores for global state, localStorage for drafts
6. **UI components**: Follow Ant Design patterns, document custom patterns
7. **Build changes**: Update Vite configuration and build scripts
8. **Environment variables**: Document new VITE_ prefixed variables

**Critical**: Update this CLAUDE.md when introducing new architectural patterns, state management approaches, or external integrations that future development sessions should understand.