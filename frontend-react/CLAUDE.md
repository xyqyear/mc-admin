# MC Admin Frontend - React Development Guide

## What This Component Is

Modern React 18 + TypeScript single-page application for MC Admin Minecraft server management. Features responsive interface with real-time updates, sophisticated three-layer data architecture, dual authentication systems, Monaco editor with Docker Compose schema validation, comprehensive backup management, player tracking with detail viewer, DNS management, advanced cron job management, file search and multi-file upload, download progress tracking, and version update notifications.

## Tech Stack

**Runtime & Build:**
- Node.js 18+ with pnpm (pnpm-lock.yaml present)
- React 18 + TypeScript 5 (strict mode)
- Vite 5 with @vitejs/plugin-react, path alias `@` → `src/`
- Dev server: port 3000 (typically already running)

**UI & Styling:**
- Ant Design 5 (v5.13.3) + @ant-design/icons + @ant-design/pro-components
- Tailwind CSS 3 + PostCSS (preflight disabled for AntD compatibility)
- Custom AntD theme with primary blue (#1677ff)
- ESLint v9 with modern flat config

**State & Data:**
- Zustand v4.5.0 with localStorage persistence (token, sidebar, login preference, downloads)
- TanStack React Query v5.85.5 (three-layer architecture)
- Axios with interceptors and auto-token injection

**Advanced Features:**
- Monaco Editor v0.52.2 + monaco-yaml v5.4.0 for Docker Compose editing
- SNBT language support for Minecraft NBT files
- React Router v6 with lazy loading and nested routes
- react-error-boundary for graceful error handling
- WebSocket integration for console streaming

## Development Commands

### Environment Setup
```bash
pnpm install    # Install dependencies (preferred)
# Alternative: npm install (fallback)
```

### Build & Quality
```bash
pnpm dev        # Start dev server (port 3000)
pnpm build      # TypeScript check + Vite bundle
pnpm lint       # ESLint check
pnpm preview    # Preview production build
```

**API Configuration**: Backend URL configured in `vite.config.ts` (default: `http://localhost:5678/api`)

## Project Structure

```
src/
├── main.tsx                 # App bootstrap with React Query, AntD theme, Monaco workers
├── App.tsx                  # Routes, error boundaries, auth wrappers
├── yaml.worker.js           # Monaco YAML worker
├── snbtLanguage.ts          # **NEW** - SNBT language definition for Monaco
│
├── components/
│   ├── layout/              # AppSidebar, MainLayout, ErrorFallback, PageHeader, DownloadTaskContainer
│   ├── overview/            # ServerStateTag, MetricCard components
│   ├── editors/             # ComposeYamlEditor, SimpleEditor, MonacoDiffEditor
│   ├── files/               # FileIcon, FileSnapshotActions
│   │
│   ├── server/              # **ENHANCED** - Server-specific components
│   │   ├── ServerOperationButtons.tsx   # Reusable operation buttons
│   │   ├── ServerTerminal.tsx           # Terminal component
│   │   ├── ServerInfoCard.tsx           # Server details
│   │   ├── ServerStatsCard.tsx          # Statistics
│   │   ├── ServerPlayersCard.tsx        # Online players
│   │   ├── ServerDiskUsageCard.tsx      # Disk usage
│   │   ├── ServerIOStatsCard.tsx        # I/O stats
│   │   ├── ServerResourcesCard.tsx      # CPU/memory monitoring
│   │   ├── ServerAddressCard.tsx        # Server address display
│   │   ├── ServerRestartScheduleCard.tsx # Restart schedule
│   │   ├── OnlinePlayersCard.tsx        # **NEW** - Real-time online players
│   │   ├── FileBreadcrumb.tsx           # File navigation
│   │   ├── DragDropOverlay.tsx          # Drag-and-drop overlay
│   │   ├── FileTable.tsx                # File listing
│   │   ├── FileToolbar.tsx              # File operations toolbar
│   │   ├── FileSearchBox.tsx            # **NEW** - File search input
│   │   ├── FileSearchResultTree.tsx     # **NEW** - Search results tree
│   │   └── HighlightedFileName.tsx      # **NEW** - Search result highlighting
│   │
│   ├── players/             # **NEW** - Player management components
│   │   ├── PlayerFilters.tsx            # Player search and filters
│   │   ├── PlayerDetailDrawer.tsx       # Player detail viewer with tabs
│   │   ├── MCAvatar.tsx                 # Minecraft player avatar
│   │   └── index.ts                     # Barrel exports
│   │
│   ├── cron/                # Cron job components
│   │   ├── CronExpressionDisplay.tsx    # Cron expression visualization
│   │   ├── CronJobFilters.tsx           # Job filtering
│   │   ├── CronJobStatusTag.tsx         # Status indicators
│   │   ├── ExecutionStatusTag.tsx       # Execution status
│   │   ├── NextRunTimeCell.tsx          # Next run display
│   │   └── index.ts
│   │
│   ├── forms/               # Advanced form builders
│   │   ├── CronExpressionBuilder.tsx    # Visual cron expression creation
│   │   ├── CronFieldInput.tsx           # Cron field inputs
│   │   └── SchemaForm.tsx               # Dynamic JSON schema forms
│   │
│   ├── debug/               # **DEV-ONLY** - Debug tools
│   │   ├── DebugModal.tsx              # Debug information modal
│   │   └── DebugTool.tsx               # Debug sidebar entry
│   │
│   ├── VersionUpdateModal.tsx          # Version update notifications
│   │
│   └── modals/              # Modal components
│       ├── ServerFiles/     # File management modals
│       │   ├── UploadModal.tsx                 # Single file upload
│       │   ├── MultiFileUploadModal.tsx        # **NEW** - Multi-file/folder upload
│       │   ├── FileUploadTree.tsx              # **NEW** - Upload tree display
│       │   ├── ConflictTree.tsx                # **NEW** - Conflict resolution tree
│       │   ├── CreateModal.tsx                 # File/folder creation
│       │   ├── RenameModal.tsx                 # File rename
│       │   ├── FileEditModal.tsx               # File editing with Monaco
│       │   ├── FileDiffModal.tsx               # File diff comparison
│       │   ├── FileDeepSearchModal.tsx         # **NEW** - Deep file search
│       │   ├── CompressionConfirmModal.tsx     # Compression confirmation
│       │   ├── CompressionResultModal.tsx      # Compression result
│       │   └── index.ts
│       ├── cron/            # Cron management modals
│       │   ├── CreateCronJobModal.tsx    # Job creation
│       │   ├── CronJobDetailModal.tsx    # Job details and logs
│       │   └── index.ts
│       ├── ArchiveSelectionModal.tsx    # Archive selection
│       ├── PopulateProgressModal.tsx    # Server population progress
│       ├── DockerComposeHelpModal.tsx   # Docker Compose help
│       ├── SHA256HelpModal.tsx          # SHA256 help
│       └── ServerTemplateModal.tsx      # Server template selection
│
├── hooks/
│   ├── api/                 # **Layer 1** - Raw API functions
│   │   ├── authApi.ts
│   │   ├── snapshotApi.ts
│   │   ├── systemApi.ts
│   │   ├── fileApi.ts        # **ENHANCED** - Multi-file upload, deep search
│   │   ├── serverApi.ts
│   │   ├── archiveApi.ts
│   │   ├── cronApi.ts
│   │   ├── dnsApi.ts
│   │   ├── configApi.ts
│   │   ├── userApi.ts
│   │   └── playerApi.ts      # **NEW** - Player management API
│   │
│   ├── queries/
│   │   ├── base/            # **Layer 2** - Resource-focused query hooks
│   │   │   ├── useServerQueries.ts
│   │   │   ├── useFileQueries.ts
│   │   │   ├── useSnapshotQueries.ts
│   │   │   ├── useArchiveQueries.ts
│   │   │   ├── useCronQueries.ts
│   │   │   ├── useDnsQueries.ts
│   │   │   ├── useConfigQueries.ts
│   │   │   ├── useSystemQueries.ts
│   │   │   ├── useUserQueries.ts
│   │   │   └── usePlayerQueries.ts   # **NEW** - Player data queries
│   │   │
│   │   └── page/            # **Layer 3** - Page-level compositions
│   │       ├── useServerDetailQueries.ts
│   │       └── useOverviewData.ts
│   │
│   ├── mutations/           # Mutation hooks
│   │   ├── useAuthMutations.ts
│   │   ├── useFileMutations.ts      # **ENHANCED** - Multi-file operations
│   │   ├── useServerMutations.ts
│   │   ├── useSnapshotMutations.ts
│   │   ├── useArchiveMutations.ts
│   │   ├── useCronMutations.ts
│   │   ├── useDnsMutations.ts
│   │   ├── useConfigMutations.ts
│   │   └── useUserMutations.ts
│   │
│   ├── useCodeLoginWebsocket.ts     # WebSocket code login
│   ├── useServerConsoleWebSocket.ts # Console WebSocket
│   ├── usePageDragUpload.ts         # Drag-and-drop validation
│   └── useVersionCheck.ts           # Version update detection
│
├── pages/                   # Route components
│   ├── Overview.tsx         # Server dashboard
│   ├── Login.tsx            # Dual authentication
│   ├── Home.tsx             # Landing page
│   ├── Snapshots.tsx        # Global snapshots
│   ├── ArchiveManagement.tsx # Archive management
│   ├── CronManagement.tsx    # Cron jobs
│   ├── DnsManagement.tsx     # DNS records
│   ├── DynamicConfig.tsx     # Dynamic configuration
│   ├── PlayerManagement.tsx  # **NEW** - Player management
│   ├── admin/
│   │   └── UserManagement.tsx
│   └── server/
│       ├── ServerNew.tsx    # Server creation
│       └── servers/
│           ├── ServerDetail.tsx    # Server overview
│           ├── ServerFiles.tsx     # **ENHANCED** - File management with search
│           ├── ServerCompose.tsx   # Docker Compose
│           └── ServerConsole.tsx   # Real-time console
│
├── stores/                  # Zustand stores
│   ├── useTokenStore.ts           # JWT token
│   ├── useSidebarStore.ts         # Navigation state
│   ├── useLoginPreferenceStore.ts # Auth method preference
│   └── useDownloadStore.ts        # **ENHANCED** - Download tasks
│
├── types/                   # TypeScript definitions
│   ├── Server.ts
│   ├── ServerInfo.ts
│   ├── ServerRuntime.ts
│   ├── MenuItem.ts
│   ├── User.ts
│   └── Dns.ts
│
├── utils/                   # Utilities
│   ├── api.ts               # Axios config, query keys, interceptors
│   ├── serverUtils.ts       # Server state utilities
│   ├── devLogger.ts         # Development logging
│   ├── fileLanguageDetector.ts # File type detection
│   ├── fileSearchUtils.ts   # **NEW** - File search utilities
│   └── downloadUtils.ts     # Download management
│
├── config/
│   ├── fileEditingConfig.ts # File editing configuration
│   ├── versionConfig.ts     # Version management (current: v0.6.2)
│   ├── snbtLanguage.ts      # **NEW** - SNBT language config for Monaco
│   └── serverAddressConfig.ts # Server address mapping
│
└── index.css                # Tailwind directives
```

## Three-Layer Data Architecture

**Layer 1: API Layer** (`hooks/api/`)
Raw Axios-based API functions with type safety. No caching, no side effects.

```typescript
// Example: playerApi.ts
export const fetchPlayers = async (serverId: string) => {
  const response = await api.get(`/servers/${serverId}/players`)
  return response.data
}
```

**Layer 2: Base Query Layer** (`hooks/queries/base/`)
Resource-focused React Query hooks with caching strategies.

```typescript
// Example: usePlayerQueries.ts
export const usePlayerQueries = (serverId: string) => {
  return useQuery({
    queryKey: ['players', serverId],
    queryFn: () => fetchPlayers(serverId),
    refetchInterval: 30000, // 30s for real-time updates
  })
}
```

**Layer 3: Page Query Layer** (`hooks/queries/page/`)
Composed queries for page-specific data requirements.

```typescript
// Example: useServerDetailQueries.ts
export const useServerDetailQueries = (serverId: string) => {
  const { data: serverInfo } = useServerQueries(serverId)
  const { data: players } = usePlayerQueries(serverId)
  // Compose multiple queries for the page
  return { serverInfo, players }
}
```

## Key Features

### Player Management System
**Real-time player tracking** with comprehensive detail viewer:

- Player list with search and filtering
- Player detail drawer with multiple tabs:
  - **基本信息**: UUID, name, first seen, last seen, total playtime
  - **会话记录**: Join/leave history, session durations
  - **聊天记录**: Chat messages with timestamps
  - **成就记录**: Achievement tracking
- Minecraft avatar display with skin support
- Integration with server overview for online players

**Components:**
- `PlayerManagement.tsx`: Main player management page
- `PlayerDetailDrawer.tsx`: Player detail viewer
- `MCAvatar.tsx`: Minecraft skin avatar component
- `OnlinePlayersCard.tsx`: Real-time online players in server overview

### File Management System
**Enhanced file operations** with search and multi-file upload:

- **Deep Search** (`FileDeepSearchModal.tsx`):
  - Recursive file search with regex support
  - Filter by file size and modification time
  - Tree-based search result display with highlighting
- **Multi-File Upload** (`MultiFileUploadModal.tsx`):
  - Drag-and-drop multiple files and folders
  - Upload tree visualization with file structure
  - Conflict detection and resolution strategies
  - Progress tracking for large uploads
- **SNBT Support**: Syntax highlighting for Minecraft NBT files
- **Monaco Editor**: Integrated code editing with schema validation

### DNS Management
**Multi-provider DNS** with automatic updates:

- DNS record management page (`DnsManagement.tsx`)
- Provider configuration (DNSPod, Huawei Cloud)
- Real-time DNS status monitoring
- Automatic DNS updates during server operations
- Router configuration display

### Cron Job Management
**Visual cron job system** with advanced features:

- Cron expression builder with field-by-field input
- Job creation modal with schema-driven forms
- Job detail modal with execution history and logs
- Job status tags and next run time display
- Conflict detection warnings for restart-backup conflicts

### Download Manager
**Progress tracking** for file downloads:

- Download task container in sidebar
- Real-time progress display with speed and ETA
- Download cancellation support
- State management with Zustand

### Version Update System
**Automatic version detection** with notifications:

- Version comparison and update detection
- Update modal with detailed changelog
- "Remind later" functionality (1-hour delay)
- localStorage persistence for last seen version
- Current version: **v0.6.2** (log monitoring improvements)

## State Management

### Zustand Stores

**useTokenStore**:
```typescript
interface TokenStore {
  token: string | null
  setToken: (token: string | null) => void
  clearToken: () => void
}
```

**useDownloadStore**:
```typescript
interface DownloadStore {
  tasks: DownloadTask[]
  addTask: (task: DownloadTask) => void
  updateTask: (id: string, updates: Partial<DownloadTask>) => void
  removeTask: (id: string) => void
}
```

All stores use `persist` middleware for localStorage sync.

## Authentication Flow

**Dual Authentication:**
1. **Password Login**: Traditional username/password flow
2. **WebSocket Code Login**: QR code scanning with rotating codes

**Implementation:**
- `useCodeLoginWebsocket`: WebSocket hook for code flow
- `useTokenStore`: Token persistence
- `useLoginPreferenceStore`: User's preferred auth method

## WebSocket Integration

**Console Streaming** (`useServerConsoleWebSocket`):
```typescript
const { messages, sendCommand, isConnected } = useServerConsoleWebSocket(serverId)
```

Features:
- Real-time log streaming
- Command execution via RCON
- Auto-reconnection
- Message history management

## Monaco Editor Integration

**Setup:**
- YAML worker: `yaml.worker.js`
- SNBT language: `snbtLanguage.ts` (custom language definition)
- Docker Compose schema validation
- Syntax highlighting for server files

**File Type Support:**
- YAML (Docker Compose with schema)
- JSON, JavaScript, TypeScript
- Python, Java, Shell scripts
- Properties files
- **SNBT** (Minecraft NBT format)

## Caching Strategies

**Query Refetch Intervals:**
- **Real-time data** (players, online status): 30s
- **Moderate updates** (resources, stats): 60s
- **Slow changes** (snapshots, archives): 2min
- **Static data** (server config): Manual refetch

**Intelligent Invalidation:**
- Mutations invalidate related queries automatically
- Server operations trigger full data refresh
- File operations invalidate file list queries

## Development Patterns

**Component Organization:**
- Modular components with barrel exports (`index.ts`)
- Reusable UI components in `components/server/`
- Modal components grouped by feature
- Page-specific components in `pages/`

**Type Safety:**
- Strict TypeScript mode enabled
- Pydantic-compatible type definitions
- Discriminated unions for server status
- Exhaustive type checking

**Error Handling:**
- react-error-boundary for component errors
- Axios interceptors for API errors
- Toast notifications for user feedback
- Fallback UI for error states

## External Documentation

Use Context7 MCP tool:
- React: `/facebook/react`
- Ant Design: `/ant-design/ant-design`
- TanStack Query: `/tanstack/query`
- Monaco Editor: `/microsoft/monaco-editor`
- React Router: `/remix-run/react-router`
- Zustand: `/pmndrs/zustand`

Resolve library ID first, then fetch docs with specific topics.

## Update Instructions

When adding features:

1. **New API endpoints**: Add to `hooks/api/` directory
2. **New queries**: Add to `hooks/queries/base/` and optionally `page/`
3. **New mutations**: Add to `hooks/mutations/`
4. **New components**: Organize by feature in `components/`
5. **New pages**: Add to `pages/` with lazy loading in `App.tsx`
6. **New types**: Add to `types/` directory
7. **New utilities**: Add to `utils/` directory
8. **Version updates**: Update `config/versionConfig.ts` with changelog
9. **Update this CLAUDE.md** with new patterns and components

**Important Guidelines:**
- Write complete documentation, not incremental patches
- Reflect actual implementation, not planned features
- Ensure consistency with main `CLAUDE.md` and `backend/CLAUDE.md`
- Check git history before updating to capture all changes since last doc update

Keep this file updated to help future development sessions understand the frontend architecture, component organization, and development patterns.
