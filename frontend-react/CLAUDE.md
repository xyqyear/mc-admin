# MC Admin Frontend - React Development Guide

## What This Component Is

Modern React 18 + TypeScript single-page application providing the web UI for MC Admin Minecraft server management. Features a responsive interface with real-time updates, sophisticated three-layer data management architecture, dual authentication systems, and fully integrated Monaco editor with Docker Compose schema validation.

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
│   ├── layout/              # AppSidebar, MainLayout, ErrorFallback, LoadingSpinner
│   ├── overview/            # ServerStateTag, SimpleMetricCard, ProgressMetricCard  
│   └── editors/             # ComposeYamlEditor, SimpleEditor, MonacoDiffEditor (+ index.ts)
├── hooks/
│   ├── api/serverApi.ts     # Raw Axios-based API functions with type safety
│   ├── queries/             # React Query hooks: useServerQueries, useServerDetailQueries, useServerPageQueries
│   ├── mutations/           # React Query mutations: useServerMutations
│   ├── useLoginApi.ts       # Traditional password-based authentication
│   └── useCodeLoginApi.ts   # WebSocket code-based authentication
├── pages/                   # Route components: Overview, Login, Home, Backups, server/[id]/* pages
├── stores/                  # Zustand stores: useTokenStore, useSidebarStore, useLoginPreferenceStore
├── types/                   # TypeScript definitions: Server, ServerInfo, ServerRuntime, MenuItem
├── utils/                   # api.ts (axios config + query keys), serverUtils.ts, devLogger.ts
├── data/mockData.ts         # Comprehensive development/testing data
└── index.css                # Tailwind directives and base styles
```

### Three-Layer Data Architecture (Actual Implementation)

**Layer 1: API Layer** (`hooks/api/serverApi.ts`):
- Raw Axios functions with full type safety (e.g., `serverApi.getServerInfo`, `systemApi.getSystemInfo`)
- HTTP client configuration with request/response interceptors
- Automatic JWT token injection and 401 handling
- Type-safe request/response interfaces for all endpoints
- **Recent Update**: Separated disk usage and I/O statistics APIs

**Layer 2: Query Hooks** (`hooks/queries/`):
- **`useServerQueries.ts`**: Base React Query hooks with intelligent caching strategies  
- Different stale times and refetch intervals based on data volatility:
  - Server configs: 5min stale time (rarely change)
  - Server status: 10s refetch interval (frequent updates needed)
  - Server runtime: 3-5s refetch interval (real-time monitoring)
  - **Disk usage**: 30s refetch interval (always available, independent of server status)
  - Players/resources: Conditional queries (only when server is healthy/running)
- Smart error retry logic with 4xx differentiation (don't retry auth errors)

**Layer 3: Composed Query Hooks** (`useServerDetailQueries.ts`, `useServerPageQueries.ts`):
- **`useServerDetailData()`**: Combines server info, status, runtime, and resources for detail pages
- **`useOverviewData()`**: Combines server list with system info for overview dashboard
- **`useServerPageQueries()`**: Page-specific query compositions with dependency management
- Intelligent dependency chains (e.g., runtime queries only enabled when status is available)
- Centralized loading states and error handling for complex pages

### API Integration Updates

**Separated Disk Usage API (Latest Changes):**
- **Problem**: Disk space was bundled with I/O stats, unavailable when servers weren't running
- **Solution**: Two focused API functions and query hooks:
  ```typescript
  // API Layer
  getServerIOStats(id: string): Promise<ServerIOStatsResponse>     // I/O performance only
  getServerDiskUsage(id: string): Promise<ServerDiskUsageResponse> // Disk space only
  
  // Query Layer
  useServerIOStats(id, status)    // Conditional on server running
  useServerDiskUsage(id)          // Always available, 30s refetch
  ```
- **Benefits**: Disk usage now displays reliably regardless of server status

**Type Definitions:**
```typescript
interface ServerIOStatsResponse {
  diskReadBytes: number;
  diskWriteBytes: number;
  networkReceiveBytes: number;
  networkSendBytes: number;
}

interface ServerDiskUsageResponse {
  diskUsageBytes: number;
  diskTotalBytes: number;
  diskAvailableBytes: number;
}
```

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
const Overview = lazy(() => import('./pages/Overview'))
const Login = lazy(() => import('./pages/Login'))
// ... etc for all route components
```

**Route Hierarchy:**
```
/ (Home) → redirects to /overview if authenticated
/login (Public route)
/overview (Server dashboard with metrics cards)
/backups (Backup management - placeholder)
/server/new (Server creation - placeholder)
/server/:id (Server detail hub)
/server/:id/players (Player management)
/server/:id/files (File management - placeholder)  
/server/:id/compose (Docker Compose configuration editing)
/server/:id/console (Real-time console with WebSocket)
```

**Features:**
- **Protected Routes**: Authentication wrapper with automatic redirects
- **Future Flags**: `v7_startTransition` and `v7_relativeSplatPath` enabled for React Router v7 prep
- **Error Boundaries**: Each route wrapped with error boundary for graceful failure
- **Dynamic Navigation**: Sidebar auto-generates server routes based on available servers

### Dual Authentication System

**1. Traditional Password Authentication** (`hooks/useLoginApi.ts`):
- Username/password form submission with FormData
- OAuth2 password flow to `/auth/token` endpoint
- JWT token storage and automatic redirection on success
- Standard form validation and error handling

**2. WebSocket Code Authentication** (`hooks/useCodeLoginApi.ts`):
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

**Custom Component Library:**

1. **Metric Components**:
   - **`SimpleMetricCard`**: Clean metric display with labels and values
   - **`ProgressMetricCard`**: Progress bars with color coding and status indicators
   - **`ServerStateTag`**: Server status visualization with icons and tooltips

2. **Layout Components**:
   - **`MainLayout`**: Standard sidebar + content layout with responsive design
   - **`AppSidebar`**: Dynamic navigation with server-aware menu items
   - **`LoadingSpinner`**: Flexible loading component with multiple display modes
   - **`ErrorFallback`**: Error boundary fallback with user-friendly error display

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
  }
  // ... hierarchical, stable structure for precise cache control
}
```

**Caching Strategy by Data Type:**
- **Server Configurations**: Long cache (5 minutes) - rarely changes, expensive to fetch
- **Runtime Metrics**: Very short cache (1-3 seconds) - needs real-time updates
- **Status Information**: Medium cache (5-10 seconds) - moderate update frequency
- **Player Data**: Conditional queries - only enabled when server is healthy
- **Disk Usage**: Medium cache (30 seconds) - now always available regardless of server status

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

### Development Patterns

**Component Development:**
- **Lazy Loading**: All page components use `React.lazy()` for code splitting
- **Error Boundaries**: Strategic placement for graceful error handling
- **Hook Composition**: Custom hooks for reusable logic (auth, queries, WebSocket)
- **Type Safety**: Full TypeScript integration with backend model alignment

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

### Recent Updates & Features

**Separated Disk Usage Integration:**
- Updated `useServerDiskUsage` hook to use dedicated `/disk-usage` endpoint
- Removed disk space information from I/O statistics queries
- Enhanced reliability for disk usage displays when servers are offline
- Improved caching strategy with appropriate refetch intervals

**Query Hook Improvements:**
```typescript
// Updated hook using separated API
const useServerDiskUsage = (id: string) => {
  return useQuery({
    queryKey: [...queryKeys.serverRuntimes.detail(id), "disk"],
    queryFn: () => serverApi.getServerDiskUsage(id), // New dedicated endpoint
    enabled: !!id,
    refetchInterval: 30000, // 30s refetch - always available
    staleTime: 15000,       // 15s stale time
    retry: (failureCount, error: any) => {
      if (error?.response?.status === 404) return false; // Don't retry if server doesn't exist
      return failureCount < 3;
    },
  });
};
```

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

**Build & Deployment:**
- **Static Build**: Vite produces optimized static files for deployment
- **Environment Variables**: All config via `VITE_` prefixed variables
- **Asset Optimization**: Automatic code splitting, tree shaking, and asset optimization
- **Future Compatibility**: React Router v7 future flags enabled for smooth migration

## Development Guidelines

**Data Fetching Best Practices:**
- Use the three-layer architecture: API → Query Hooks → Composed Queries
- Choose appropriate caching strategies based on data volatility
- Implement conditional queries for features requiring specific server states
- Handle errors gracefully with appropriate retry strategies

**Performance Considerations:**
- Leverage lazy loading for route components
- Use Zustand selectors to minimize re-renders
- Implement proper query dependencies and invalidation
- Monitor bundle size and implement code splitting where needed

**Testing and Development:**
- Focus on component unit tests and integration tests
- Mock API calls appropriately for testing
- Use React Query devtools for debugging data flow
- Test authentication flows and error boundaries

## Update Instructions

When adding new features, libraries, or changing architecture:

1. **New dependencies**: Update `package.json` and document major additions in this file
2. **New routes**: Add to `App.tsx` with lazy loading and update navigation patterns
3. **New API endpoints**: Add to `hooks/api/serverApi.ts` first, then create query hooks
4. **New queries**: Extend query hooks in `hooks/queries/` following the three-layer pattern
5. **New global state**: Consider Zustand stores for global state, localStorage for drafts
6. **UI components**: Follow Ant Design patterns first, document custom component patterns
7. **Monaco editors**: Extend existing editor components or create new ones following established patterns
8. **Build configuration**: Update Vite configuration and document changes in build scripts
9. **Environment variables**: Document new `VITE_` prefixed variables and their usage
10. **WebSocket features**: Follow existing WebSocket patterns and connection management
11. **API integrations**: Document new endpoint purposes and data flow patterns
12. **Query optimizations**: Update caching strategies and refetch intervals appropriately

**Critical**: Update this CLAUDE.md when introducing new architectural patterns, state management approaches, data fetching strategies, or external integrations that future development sessions should understand and follow.