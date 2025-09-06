# MC Admin Frontend - React Development Guide

## What This Component Is

Modern React 18 + TypeScript single-page application providing the web UI for MC Admin Minecraft server management. Features a responsive interface with real-time updates, sophisticated three-layer data management architecture, dual authentication systems, fully integrated Monaco editor with Docker Compose schema validation, and comprehensive backup management with snapshot integration.

## Tech Stack

**Runtime & Build:**
- **Runtime**: Node.js 18+ with pnpm package management (pnpm-lock.yaml present)
- **Framework**: React 18 + TypeScript 5 with strict compiler options
- **Build Tool**: Vite 5 with @vitejs/plugin-react, path alias `@` → `src/`, dev port 3000 (typically already running)

**UI & Styling:**
- **UI Framework**: Ant Design 5 (`antd` v5.13.3, `@ant-design/icons`, `@ant-design/pro-components`)
- **Styling**: Tailwind CSS 3 + PostCSS + autoprefixer (preflight disabled for AntD compatibility)
- **Theme**: Custom AntD theme with primary blue (#1677ff) color scheme

**State & Data Management:**
- **State Management**: Zustand v4.5.0 with localStorage persistence middleware (3 stores)
- **Data Fetching**: TanStack React Query v5.85.5 with sophisticated three-layer caching architecture
- **API Integration**: Axios with interceptors, automatic token injection, and intelligent retry strategies

**Advanced Features:**
- **Code Editor**: Monaco Editor v0.52.2 + monaco-yaml v5.4.0 with Docker Compose schema validation
- **Routing**: React Router v6.21.3 with nested routes, lazy loading, and future flags enabled
- **Error Handling**: react-error-boundary v6.0.0 for graceful error boundaries
- **Real-time**: WebSocket integration for console streaming and authentication codes

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

**Configuration Details:**
- **API Base URL**: Configurable via `VITE_API_BASE_URL` environment variable
- **Default**: `http://localhost:5678/api` (defined in `src/utils/api.ts`)
- **WebSocket**: Automatically derives from HTTP base URL (`ws://` or `wss://`)

## Architecture Overview

### Project Structure (Actual Implementation)
```
src/
├── main.tsx                 # App bootstrap: React Query provider, AntD theme, Monaco workers
├── App.tsx                  # Routes (lazy-loaded), error boundaries, auth wrappers
├── yaml.worker.js           # Monaco Editor YAML language worker for Docker Compose
├── components/
│   ├── layout/              # AppSidebar, MainLayout, ErrorFallback, LoadingSpinner, PageHeader, ServerOperationConfirmModal
│   ├── overview/            # ServerStateTag, SimpleMetricCard, ProgressMetricCard, ServerStateIcon
│   ├── editors/             # ComposeYamlEditor, SimpleEditor, MonacoDiffEditor (+ index.ts)
│   ├── files/               # FileIcon
│   └── modals/              # ServerOperationConfirmModal
├── hooks/
│   ├── api/                 # Raw Axios-based API functions with type safety
│   │   ├── authApi.ts       # Authentication API functions
│   │   ├── snapshotApi.ts   # Snapshot management API functions  
│   │   ├── systemApi.ts     # System information API functions
│   │   ├── fileApi.ts       # File operations API functions
│   │   ├── serverApi.ts     # Server management API functions
│   │   └── userApi.ts       # User management API functions
│   ├── queries/
│   │   ├── base/            # Resource-focused query hooks
│   │   │   ├── useServerQueries.ts    # Core server data fetching
│   │   │   ├── useFileQueries.ts      # File operations queries
│   │   │   ├── useSnapshotQueries.ts  # Snapshot data queries
│   │   │   ├── useSystemQueries.ts    # System-wide queries
│   │   │   └── useUserQueries.ts      # User management queries
│   │   └── page/            # Composed page-level queries
│   │       ├── useServerDetailQueries.ts # Server detail page compositions
│   │       └── useOverviewData.ts        # Dashboard/overview compositions
│   ├── mutations/           # Organized mutation hooks
│   │   ├── useAuthMutations.ts      # Authentication operations
│   │   ├── useFileMutations.ts      # File operation mutations
│   │   ├── useServerMutations.ts    # Server management mutations
│   │   ├── useSnapshotMutations.ts  # Snapshot management mutations
│   │   └── useUserMutations.ts      # User administration mutations
│   ├── useCodeLoginWebsocket.ts     # WebSocket code-based authentication
│   └── useServerConsoleWebSocket.ts # Real-time server console integration
├── pages/                   # Route components with new snapshot management
│   ├── Overview.tsx         # Server dashboard with metrics cards
│   ├── Login.tsx            # Dual authentication interface
│   ├── Home.tsx             # Landing/redirect page
│   ├── Snapshots.tsx        # **NEW** - Global snapshot management page
│   ├── admin/
│   │   └── UserManagement.tsx
│   └── server/
│       ├── new.tsx          # Server creation
│       └── servers/         # **UPDATED** - Reorganized server pages
│           ├── index.tsx    # Server detail hub (formerly server/[id]/index.tsx)
│           ├── files.tsx    # File management (formerly server/[id]/files.tsx)
│           ├── compose.tsx  # Docker Compose configuration (formerly server/[id]/compose.tsx)
│           └── console.tsx  # Real-time console (formerly server/[id]/console.tsx)
├── stores/                  # Zustand stores with persistence
│   ├── useTokenStore.ts           # JWT token management
│   ├── useSidebarStore.ts         # Navigation state
│   └── useLoginPreferenceStore.ts # Authentication method preference
├── types/                   # TypeScript definitions
│   ├── Server.ts            # Core server types and status definitions
│   ├── ServerInfo.ts        # Server configuration and metadata
│   ├── ServerRuntime.ts     # Runtime metrics and resource data
│   ├── MenuItem.ts          # Navigation menu item definitions
│   └── User.ts              # User management and authentication types
├── utils/                   # Core utilities
│   ├── api.ts               # Axios configuration, query keys, request/response interceptors
│   ├── serverUtils.ts       # Server state and utility functions
│   ├── devLogger.ts         # Development logging utilities
│   └── fileLanguageDetector.ts # File type detection for editors
├── config/
│   └── fileEditingConfig.ts # File editing configuration and validation
├── data/mockData.ts         # Comprehensive development/testing data
└── index.css                # Tailwind directives and base styles
```

### Three-Layer Data Architecture (Enhanced Implementation)

**Layer 1: API Layer** (`hooks/api/`):
Raw Axios functions with full type safety, organized by domain:
- **`authApi.ts`**: Authentication operations (login, registration, token verification)
- **`snapshotApi.ts`**: Backup and snapshot management (create, list, restore snapshots)
- **`systemApi.ts`**: System information and resource monitoring
- **`serverApi.ts`**: Server management, configuration, and runtime data
- **`fileApi.ts`**: File operations (read, write, upload, delete)
- **`userApi.ts`**: User administration and profile management

Each API file provides:
- HTTP client configuration with request/response interceptors
- Automatic JWT token injection and 401 handling
- Type-safe request/response interfaces for all endpoints

**Layer 2: Base Query Layer** (`hooks/queries/base/`):
Resource-focused React Query hooks with intelligent caching strategies:
- **`useServerQueries.ts`**: Server data fetching with different stale times and refetch intervals
- **`useFileQueries.ts`**: File operations queries with conditional loading
- **`useSnapshotQueries.ts`**: Snapshot data with 2-minute stale time for backup operations
- **`useSystemQueries.ts`**: System resource monitoring queries
- **`useUserQueries.ts`**: User management and authentication queries

Caching strategy by data type:
- Server configs: 5min stale time (rarely change)
- Server status: 10s refetch interval (frequent updates needed)
- Server runtime: 3-5s refetch interval (real-time monitoring)
- Snapshot data: 2min stale time (manual refresh pattern)
- Disk usage: 30s refetch interval (always available)
- Players/resources: Conditional queries (only when server is healthy/running)

**Layer 3: Page Query Layer** (`hooks/queries/page/`):
Composed page-level queries combining multiple base queries:
- **`useServerDetailQueries.ts`**: Server detail page data composition
- **`useOverviewData.ts`**: Dashboard overview with server list and system metrics

Features:
- Intelligent dependency chains (runtime queries only enabled when status is available)
- Centralized loading states and error handling for complex pages
- Optimized data fetching patterns for specific page requirements

### Mutation Architecture (`hooks/mutations/`)

Organized mutation hooks separated by domain for better maintainability:

- **`useAuthMutations.ts`**: User authentication, registration, and login operations
- **`useFileMutations.ts`**: File operations (create, update, delete, upload, rename)
- **`useServerMutations.ts`**: Server lifecycle management (start, stop, restart, configuration updates)
- **`useSnapshotMutations.ts`**: Backup creation and management operations
- **`useUserMutations.ts`**: User administration and profile updates

Each mutation hook provides:
- Optimistic updates where appropriate
- Automatic query invalidation on success
- Error handling with user-friendly feedback
- Loading states and progress indicators

### State Management (Zustand Stores)

**Three Primary Stores with localStorage Persistence:**

1. **Token Store** (`stores/useTokenStore.ts`):
   - JWT token persistence with automatic localStorage sync
   - Authentication state management (`isAuthenticated()`, `setToken()`, `clearToken()`)
   - Selector hooks for performance optimization
   - Automatic token injection via axios interceptors

2. **Sidebar Store** (`stores/useSidebarStore.ts`):
   - Dynamic navigation state (open menu keys, collapsed state)
   - Auto-updates based on current route with path-based key generation
   - Persistent sidebar state across browser sessions
   - Server-aware navigation (menu items dynamically generated from server list)

3. **Login Preference Store** (`stores/useLoginPreferenceStore.ts`):
   - User preference for authentication method ('password' vs 'code')
   - Persistent choice between traditional login and WebSocket code flow
   - Simple toggle functionality with localStorage backing

**Store Architecture:**
- All stores use Zustand with persistence middleware
- Exported selector hooks for preventing unnecessary re-renders
- Version handling for localStorage migration support
- JSON serialization with automatic type restoration

### Routing Structure (React Router v6)

**Route Organization with Lazy Loading:**
```typescript
// All pages are lazy-loaded for performance
const Overview = lazy(() => import('@/pages/Overview'))
const Login = lazy(() => import('@/pages/Login'))
const Snapshots = lazy(() => import('@/pages/Snapshots'))
// ... etc for all route components
```

**Updated Route Hierarchy:**
```
/ (Home) → redirects to /overview if authenticated
/login (Public route)
/overview (Server dashboard with metrics cards)
/snapshots (Global snapshot management - **NEW**)
/server/new (Server creation)
/server/:id (Server detail hub)
/server/:id/files (File management with Monaco editor)
/server/:id/compose (Docker Compose configuration editing)
/server/:id/console (Real-time console with WebSocket)
/admin/users (User management - OWNER role only)
```

**Route Changes:**
- **New `/snapshots` route**: Global backup management page
- **Reorganized server pages**: Moved from `/server/[id]/` to `/server/servers/` structure
- **Enhanced navigation**: Automatic snapshot menu integration
- **Role-based access**: Admin routes with proper role guards

**Features:**
- **Protected Routes**: Authentication wrapper with automatic redirects
- **Future Flags**: `v7_startTransition` and `v7_relativeSplatPath` enabled for React Router v7 prep
- **Error Boundaries**: Each route wrapped with error boundary for graceful failure
- **Dynamic Navigation**: Sidebar auto-generates server routes based on available servers

### Snapshot Management Integration

**New Snapshot Management System:**
- **Global Snapshots Page** (`pages/Snapshots.tsx`): Complete snapshot management interface
- **Snapshot API Integration** (`hooks/api/snapshotApi.ts`): Restic backup operations
- **Snapshot Queries** (`hooks/queries/base/useSnapshotQueries.ts`): Data fetching for snapshots
- **Snapshot Mutations** (`hooks/mutations/useSnapshotMutations.ts`): Backup creation and management
- **Navigation Integration**: Snapshots menu item in sidebar with automatic navigation

**Snapshot Features:**
- Create global system snapshots with progress tracking
- View snapshot history with metadata (size, date, duration)
- Real-time snapshot creation feedback with success/error handling
- Intelligent caching with 2-minute stale time and manual refresh pattern
- Integration with existing server management workflow

### Dual Authentication System

**1. Traditional Password Authentication** (`hooks/mutations/useAuthMutations.ts`):
- Username/password form submission with FormData
- OAuth2 password flow to `/auth/token` endpoint
- JWT token storage and automatic redirection on success
- Standard form validation and error handling

**2. WebSocket Code Authentication** (`hooks/useCodeLoginWebsocket.ts`):
- Real-time 8-digit code generation via WebSocket connection to `/auth/code`
- Auto-refreshing codes with countdown timers (60-second TTL)
- Connection state management (IDLE, CONNECTING, CONNECTED, ERROR)
- WebSocket URL auto-derivation from HTTP base URL
- External verification flow using master token system

**Authentication Flow Integration:**
- User preference stored in `useLoginPreferenceStore`
- Login page dynamically switches between modes
- JWT token handling is identical regardless of authentication method
- Automatic axios interceptor setup for API authentication

### Monaco Editor Integration

**Multi-Worker Architecture:**
- **Worker Configuration**: Pre-configured workers in `main.tsx` for JSON, CSS, HTML, TypeScript, and YAML
- **Custom YAML Worker**: `yaml.worker.js` with Docker Compose schema support
- **MonacoEnvironment**: Proper worker initialization and path resolution

**Three Editor Components:**

1. **`ComposeYamlEditor`**: 
   - Specialized for Docker Compose files with schema validation
   - YAML syntax highlighting with error detection
   - Real-time validation and intelligent autocompletion
   - Integration with server compose configuration API

2. **`SimpleEditor`**: 
   - General-purpose code editor for various file types
   - Configurable language support and themes
   - Basic editing features with syntax highlighting

3. **`MonacoDiffEditor`**: 
   - Side-by-side diff comparison with syntax highlighting
   - Useful for configuration changes and version comparison

**Advanced Features:**
- **Schema Validation**: Docker Compose schema for intelligent suggestions
- **Local Draft Support**: localStorage integration for unsaved changes
- **Consistency Checking**: Compare local drafts with server state
- **Custom Themes**: Configurable editor appearance

### UI Component Architecture

**Ant Design Integration:**
- **Primary UI Library**: Ant Design 5 as the foundation with custom theme
- **Theme Customization**: Primary color (#1677ff), spacing, and component styles
- **Component Usage**: Cards, Forms, Tables, Modals, Notifications
- **Pro Components**: Advanced components for data display and input

**Enhanced Custom Component Library:**

1. **Metric Components**:
   - **`SimpleMetricCard`**: Clean metric display with labels and values
   - **`ProgressMetricCard`**: Progress bars with color coding and status indicators
   - **`ServerStateTag`**: Server status visualization with icons and tooltips
   - **`ServerStateIcon`**: Reusable server status icons

2. **Layout Components**:
   - **`MainLayout`**: Standard sidebar + content layout with responsive design
   - **`AppSidebar`**: Dynamic navigation with server-aware menu items and snapshot integration
   - **`PageHeader`**: **NEW** - Standardized page header component for consistency
   - **`LoadingSpinner`**: Flexible loading component with multiple display modes
   - **`ErrorFallback`**: Error boundary fallback with user-friendly error display

3. **Modal Components**:
   - **`ServerOperationConfirmModal`**: **NEW** - Reusable confirmation modals for server operations

**Styling Strategy:**
- **Ant Design First**: Use AntD components as primary building blocks
- **Tailwind Utilities**: Only for spacing, layout, and minor visual adjustments
- **No Preflight**: Tailwind preflight disabled in `tailwind.config.js` to prevent AntD conflicts
- **Responsive Design**: Grid-based layouts with mobile-first approach

## React Query Configuration

**Global Configuration** (in `main.tsx`):
```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,  // 5 minutes default stale time
      retry: (failureCount, error) => {
        // Smart retry: don't retry 4xx errors except 408/429
        if (error.response?.status >= 400 && error.response?.status < 500) {
          return error.response.status === 408 || error.response.status === 429
        }
        return failureCount < 3
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,  // No automatic retry for mutations
    },
  },
})
```

**Query Key Factory** (from `utils/api.ts`):
```typescript
export const queryKeys = {
  serverInfos: {
    lists: () => ['serverInfos'],
    detail: (id: string) => ['serverInfos', id]
  },
  serverStatuses: {
    detail: (id: string) => ['serverStatuses', id]
  },
  serverRuntimes: {
    detail: (id: string) => ['serverRuntimes', id]
  },
  snapshots: {
    global: () => ['snapshots', 'global'],
    server: (id: string) => ['snapshots', 'server', id]
  }
  // ... hierarchical, stable structure for precise cache control
}
```

**Enhanced Caching Strategy by Data Type:**
- **Server Configurations**: Long cache (5 minutes) - rarely changes, expensive to fetch
- **Runtime Metrics**: Very short cache (1-3 seconds) - needs real-time updates
- **Status Information**: Medium cache (5-10 seconds) - moderate update frequency
- **Snapshot Data**: Medium cache (2 minutes) - manual refresh pattern for backup operations
- **Player Data**: Conditional queries - only enabled when server is healthy
- **Disk Usage**: Medium cache (30 seconds) - always available regardless of server status

### WebSocket Integration

**Real-time Features:**
- **Console Streaming**: Live log output via WebSocket connection to `/servers/{id}/console`
- **Authentication Codes**: Live code generation and auto-refresh via `/auth/code`
- **Connection Management**: Auto-reconnection, heartbeat, and graceful error handling

**WebSocket Implementation:**
- **URL Derivation**: Automatic HTTP→WS and HTTPS→WSS conversion from `VITE_API_BASE_URL`
- **State Management**: Connection status tracking (IDLE, CONNECTING, CONNECTED, ERROR)
- **Error Recovery**: Automatic reconnection with exponential backoff
- **Message Protocol**: JSON-based message handling with type safety

### Import System Transformation

**Absolute Import System:**
All relative imports have been converted to use the `@/` alias for better maintainability:

**Before:**
```typescript
import { serverApi } from '../api/serverApi'
import { LoadingSpinner } from './layout/LoadingSpinner'
import ServerStateTag from '../overview/ServerStateTag'
```

**After:**
```typescript
import { serverApi } from '@/hooks/api/serverApi'
import { LoadingSpinner } from '@/components/layout/LoadingSpinner'
import ServerStateTag from '@/components/overview/ServerStateTag'
```

**Benefits:**
- **Consistency**: All imports use the same absolute path structure
- **Maintainability**: Moving files doesn't break imports
- **Readability**: Clear distinction between project files and external dependencies
- **IDE Support**: Better autocomplete and refactoring support

### Development Patterns

**Component Development:**
- **Lazy Loading**: All page components use `React.lazy()` for code splitting
- **Error Boundaries**: Strategic placement for graceful error handling
- **Hook Composition**: Custom hooks for reusable logic (auth, queries, WebSocket)
- **Type Safety**: Full TypeScript integration with backend model alignment
- **Absolute Imports**: Consistent use of `@/` alias for all internal imports

**Performance Optimization:**
- **Query Optimization**: Intelligent caching, selective refetching, and dependency management
- **State Selectors**: Zustand selector hooks to minimize re-renders
- **Monaco Workers**: Offload editor processing to web workers
- **Code Splitting**: Route-level and feature-level code splitting

**Error Handling Strategy:**
- **React Error Boundary**: Global error catching with user-friendly fallback
- **Query Error Handling**: Differentiated retry logic and error state management
- **User Feedback**: Toast notifications, error alerts, and loading states
- **Graceful Degradation**: Fallback behavior when features are unavailable

## External Documentation

**Always use Context7 for external library documentation:**

**Key Context7 Library IDs:**
- **Ant Design**: `/ant-design/ant-design`
- **React**: `/facebook/react`
- **TanStack Query**: `/tanstack/query`  
- **React Router**: `/remix-run/react-router`
- **Zustand**: `/pmndrs/zustand`
- **Vite**: `/vitejs/vite`
- **Monaco Editor**: `/microsoft/monaco-editor`
- **Tailwind CSS**: `/tailwindlabs/tailwindcss`
- **TypeScript**: `/microsoft/TypeScript`

**Process**: 
1. Use `mcp__context7__resolve-library-id` to find the correct library ID
2. Use `mcp__context7__get-library-docs` with specific topics (hooks, theming, configuration, etc.)

## Integration Notes

**Backend Integration:**
- **API Connection**: Connects to FastAPI backend at configurable base URL (default: http://localhost:5678/api)
- **WebSocket**: Auto-derived from HTTP base URL for real-time console and authentication
- **CORS**: Backend configured for localhost:3000 development with credentials support
- **Authentication**: JWT token system with master token fallback support
- **API Reliability**: Separated disk usage and I/O statistics APIs for better data availability
- **Snapshot Integration**: Complete integration with backend Restic snapshot system

**Build & Deployment:**
- **Static Build**: Vite produces optimized static files for deployment
- **Environment Variables**: All config via `VITE_` prefixed variables
- **Asset Optimization**: Automatic code splitting, tree shaking, and asset optimization
- **Future Compatibility**: React Router v7 future flags enabled for smooth migration

## Development Guidelines

**Data Fetching Best Practices:**
- Use the three-layer architecture: API → Base Query Hooks → Page Query Compositions
- Choose appropriate caching strategies based on data volatility
- Implement conditional queries for features requiring specific server states
- Handle errors gracefully with appropriate retry strategies
- Separate mutations by domain for better organization

**Performance Considerations:**
- Leverage lazy loading for route components
- Use Zustand selectors to minimize re-renders
- Implement proper query dependencies and invalidation
- Monitor bundle size and implement code splitting where needed
- Use absolute imports for better maintainability

**Testing and Development:**
- Focus on component unit tests and integration tests
- Mock API calls appropriately for testing
- Use React Query devtools for debugging data flow
- Test authentication flows and error boundaries

## Update Instructions

When adding new features, libraries, or changing architecture:

1. **New dependencies**: Update `package.json` and document major additions in this file
2. **New routes**: Add to `App.tsx` with lazy loading and update navigation patterns
3. **New API endpoints**: Add to appropriate API file in `hooks/api/` first, then create query/mutation hooks
4. **New queries**: Extend base query hooks in `hooks/queries/base/` and compose in page queries
5. **New mutations**: Create domain-specific mutation hooks in `hooks/mutations/`
6. **New global state**: Consider Zustand stores for global state, localStorage for drafts
7. **UI components**: Follow Ant Design patterns first, document custom component patterns
8. **Monaco editors**: Extend existing editor components or create new ones following established patterns
9. **Build configuration**: Update Vite configuration and document changes in build scripts
10. **Environment variables**: Document new `VITE_` prefixed variables and their usage
11. **WebSocket features**: Follow existing WebSocket patterns and connection management
12. **API integrations**: Document new endpoint purposes and data flow patterns
13. **Query optimizations**: Update caching strategies and refetch intervals appropriately
14. **Import consistency**: Use absolute imports (`@/`) for all new files and components

**IMPORTANT EDITING GUIDELINES:**

**Before updating any CLAUDE.md file:**
1. **Check git history** to identify the last CLAUDE.md update commit: `git log --oneline --follow -- CLAUDE.md | head -5`
2. **Compare current state** with the last CLAUDE.md update: `git diff <last_commit>..HEAD --name-status`
3. **Analyze all changes** made since the last documentation update to ensure complete coverage
4. **Review new files, modified functionality, and architectural changes** to capture all relevant updates

**When writing CLAUDE.md updates:**
1. **Write complete, self-contained documentation** - each version should be fully accurate and comprehensive
2. **Avoid incremental/patch-like language** such as "Recent changes," "Latest updates," or "New additions"
3. **Integrate all information naturally** into the existing structure rather than appending changelog-style entries
4. **Ensure consistency** between all three CLAUDE.md files (main, backend, frontend) regarding shared concepts
5. **Reflect actual codebase state** - documentation should describe what IS, not what WAS or what changed

This approach ensures each CLAUDE.md version stands alone as complete project documentation rather than appearing as a series of patches or incremental updates.

**Critical**: Update this CLAUDE.md when introducing new architectural patterns, state management approaches, data fetching strategies, snapshot management features, or external integrations that future development sessions should understand and follow.