# MC Admin Frontend - React Development Guide

## What This Component Is

Modern React 19 + TypeScript single-page application for MC Admin Minecraft server management. Features responsive interface with real-time updates, sophisticated three-layer data architecture, dual authentication systems, Monaco editor with Docker Compose schema validation, comprehensive backup management, player tracking with detail viewer, DNS management, advanced cron job management, file search and multi-file upload, download progress tracking, background task center for long-running operations, server template system with typed variable forms and mode conversion, version update notifications, and direct container terminal access.

## Tech Stack

**Runtime & Build:**

- Node.js 18+ with pnpm (pnpm-lock.yaml present)
- React 19 + TypeScript 5 (strict mode)
- Vite 5 with @vitejs/plugin-react, path alias `@` → `src/`
- Dev server: port 3000 (typically already running)

**UI & Styling:**

- shadcn/ui built on `@base-ui/react` primitives (not Radix) with `useRender` + `render` prop pattern
- Tailwind CSS v4 with CSS-only config (no `tailwind.config.js`), OKLCH color space via CSS variables
- Lucide icons throughout
- `@rjsf/shadcn` for schema-driven forms
- Sonner for toast notifications
- ESLint v9 with modern flat config

**State & Data:**

- Zustand v4.5.7 with localStorage persistence (token, sidebar, login preference, downloads)
- TanStack React Query v5.89.0 (three-layer architecture)
- Axios with interceptors and auto-token injection

**Advanced Features:**

- Monaco Editor v0.52.2 + monaco-yaml v5.4.0 for Docker Compose editing
- Docker Compose schema with docker-minecraft-server specific hints
- SNBT language support for Minecraft NBT files
- React Router v6 with lazy loading and nested routes
- react-error-boundary for graceful error handling
- WebSocket integration for console streaming
- xterm.js for terminal emulation with direct container attach

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

```text
src/
├── main.tsx                 # App bootstrap with React Query, TooltipProvider, sonner Toaster, Monaco workers
├── App.tsx                  # Routes, error boundaries, auth wrappers
├── yaml.worker.js           # Monaco YAML worker
├── snbtLanguage.ts          # SNBT language definition for Monaco
│
├── components/
│   ├── ui/                  # shadcn/ui components (button, card, dialog, sidebar, etc.)
│   ├── layout/              # AppSidebar, MainLayout, ErrorFallback, PageHeader, LoadingSpinner
│   ├── overview/            # ServerStateIcon, MetricCard components
│   ├── editors/             # ComposeYamlEditor, SimpleEditor, MonacoDiffEditor
│   ├── files/               # FileIcon (Lucide-based), FileSnapshotActions
│   ├── map/                 # ServerMap (Leaflet), ServerMapTileLayer (authed GridLayer), coords helpers, MapHelpButton
│   ├── world-restore/       # WorldRestoreSelectionPanel, SnapshotPicker, RestorePreviewModal (mini Leaflet + PreviewTileLayer), RestorationHistoryDrawer, ServerStopGuard, RestoreProgressCard, restoreProgress reducer, selectionUtils
│   │
│   ├── task-center/         # Background task UI
│   │   ├── TaskCenterTrigger.tsx       # Fixed Button with badge
│   │   ├── TaskCenterPanel.tsx         # Card panel with tabs
│   │   ├── BackgroundTaskList.tsx      # List of background tasks
│   │   ├── BackgroundTaskItem.tsx      # Individual task item
│   │   ├── DownloadTaskList.tsx        # Download tasks tab
│   │   ├── DownloadTaskItem.tsx        # Individual download item
│   │   └── index.ts
│   │
│   ├── server/              # Server-specific components
│   │   ├── ServerOperationButtons.tsx   # Reusable operation buttons
│   │   ├── ServerTerminal.tsx           # Terminal component with xterm.js
│   │   ├── ServerInfoCard.tsx           # Server details
│   │   ├── ServerStatsCard.tsx          # Statistics
│   │   ├── ServerPlayersCard.tsx        # Online players
│   │   ├── ServerDiskUsageCard.tsx      # Disk usage
│   │   ├── ServerIOStatsCard.tsx        # I/O stats
│   │   ├── ServerResourcesCard.tsx      # CPU/memory monitoring
│   │   ├── ServerAddressCard.tsx        # Server address display
│   │   ├── ServerRestartScheduleCard.tsx # Restart schedule
│   │   ├── OnlinePlayersCard.tsx        # Real-time online players
│   │   ├── FileBreadcrumb.tsx           # File navigation
│   │   ├── DragDropOverlay.tsx          # Drag-and-drop overlay
│   │   ├── FileTable.tsx                # File listing
│   │   ├── FileToolbar.tsx              # File operations toolbar
│   │   ├── FileSearchBox.tsx            # File search input
│   │   ├── FileSearchResultTree.tsx     # Search results tree
│   │   ├── HighlightedFileName.tsx      # Search result highlighting
│   │   ├── ServerNew/                   # Server creation sub-components
│   │   │   ├── TemplateCreationMode.tsx # Template-based server creation
│   │   │   └── TraditionalCreationMode.tsx # Traditional YAML creation
│   │   └── ServerCompose/               # Server compose editing sub-components
│   │       ├── TemplateMode.tsx         # Template variable form editing
│   │       └── DirectMode.tsx           # Direct YAML editing
│   │
│   ├── common/              # Shared components
│   │   ├── DataTable.tsx                # TanStack Table wrapper
│   │   ├── SortableHeader.tsx           # Sortable column header
│   │   ├── StatusBadge.tsx              # Tone-based status badge
│   │   ├── EmptyState.tsx               # Empty list placeholder
│   │   ├── PlayerOnlineBadge.tsx        # Online/offline dot badge
│   │   ├── RefreshButton.tsx            # Unified refresh button with spin-on-load
│   │   └── ServerNameTag.tsx            # Clickable server name tags
│   │
│   ├── players/             # Player management components
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
│   │   ├── SchemaForm.tsx               # Dynamic JSON schema forms
│   │   └── rjsfTheme.tsx                # Re-export of @rjsf/shadcn Theme as default form
│   │
│   ├── debug/               # **DEV-ONLY** - Debug tools
│   │   ├── DebugModal.tsx              # Debug information modal
│   │   └── DebugTool.tsx               # Debug sidebar entry
│   │
│   ├── templates/             # Template management components
│   │   ├── VariableDefinitionForm.tsx  # Variable definition editor
│   │   ├── variableUtils.ts           # Variable form data conversion
│   │   └── index.ts
│   │
│   ├── VersionUpdateModal.tsx          # Version update notifications with issue links
│   │
│   └── modals/              # Modal components
│       ├── ServerFiles/     # File management modals
│       │   ├── MultiFileUploadModal.tsx        # Multi-file/folder upload
│       │   ├── FileUploadTree.tsx              # Upload tree display
│       │   ├── ConflictTree.tsx                # Conflict resolution tree
│       │   ├── CreateModal.tsx                 # File/folder creation
│       │   ├── RenameModal.tsx                 # File rename
│       │   ├── FileEditModal.tsx               # File editing with Monaco
│       │   ├── FileDiffModal.tsx               # File diff comparison
│       │   ├── FileDeepSearchModal.tsx         # Deep file search
│       │   ├── CompressionConfirmModal.tsx     # Compression confirmation
│       │   ├── CompressionResultModal.tsx      # Compression result
│       │   └── index.ts
│       ├── cron/            # Cron management modals
│       │   ├── CreateCronJobModal.tsx    # Job creation
│       │   ├── CronJobDetailModal.tsx    # Job details and logs
│       │   └── index.ts
│       ├── ArchiveSelectionModal.tsx    # Archive selection
│       ├── PopulateProgressModal.tsx    # Server population progress
│       ├── RebuildProgressModal.tsx     # Server rebuild progress (template updates)
│       ├── ConvertModeModal.tsx         # Template ↔ direct mode conversion wizard
│       ├── DockerComposeHelpModal.tsx   # Docker Compose help
│       ├── SHA256HelpModal.tsx          # SHA256 help
│       ├── ServerOperationConfirmModal.tsx # Server operation confirmation
│       ├── ServerTemplateModal.tsx      # Existing server compose selection
│       ├── SyncWithFilesystemDialog.tsx # Filesystem ↔ DB sync preview/apply (OWNER-only)
│       └── ServerCompose/
│           └── ComposeDiffModal.tsx     # YAML diff viewer (Monaco diff editor)
│
├── hooks/
│   ├── api/                 # **Layer 1** - Raw API functions
│   │   ├── authApi.ts
│   │   ├── snapshotApi.ts   # Includes deletion and unlock APIs
│   │   ├── systemApi.ts
│   │   ├── fileApi.ts       # Multi-file upload, deep search
│   │   ├── serverApi.ts
│   │   ├── archiveApi.ts
│   │   ├── cronApi.ts
│   │   ├── dnsApi.ts
│   │   ├── configApi.ts
│   │   ├── userApi.ts
│   │   ├── playerApi.ts     # Player management API
│   │   ├── taskApi.ts       # Background task API
│   │   ├── templateApi.ts   # Template CRUD, config, conversion, preview
│   │   └── worldRestoreApi.ts # Layout, eligible snapshots, snapshot create, preview heartbeat/end, tile URL builder, restoration list/detail
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
│   │   │   ├── usePlayerQueries.ts   # Player data queries
│   │   │   ├── useTaskQueries.ts     # Background task queries with polling
│   │   │   ├── useTemplateQueries.ts # Template list, detail, schema, config, ports
│   │   │   └── useWorldRestoreQueries.ts # World layout, eligible snapshots, restoration history, restoration detail
│   │   │
│   │   └── page/            # **Layer 3** - Page-level compositions
│   │       ├── useServerDetailQueries.ts
│   │       └── useOverviewData.ts
│   │
│   ├── mutations/           # Mutation hooks
│   │   ├── useAuthMutations.ts
│   │   ├── useFileMutations.ts      # Multi-file operations
│   │   ├── useServerMutations.ts
│   │   ├── useSnapshotMutations.ts  # Includes deletion and unlock
│   │   ├── useArchiveMutations.ts
│   │   ├── useCronMutations.ts
│   │   ├── useDnsMutations.ts
│   │   ├── useConfigMutations.ts
│   │   ├── useUserMutations.ts
│   │   ├── usePlayerMutations.ts
│   │   ├── useTaskMutations.ts
│   │   ├── useTemplateMutations.ts  # Template CRUD, config update, mode conversion
│   │   └── useWorldRestoreMutations.ts # World snapshot creation, preview heartbeat/end
│   │
│   ├── useCodeLoginWebsocket.ts     # WebSocket code login
│   ├── useServerConsoleWebSocket.ts # Console WebSocket with direct attach
│   ├── usePageDragUpload.ts         # Drag-and-drop validation
│   ├── useEventStream.ts            # Reusable SSE consumer (auth-aware fetch + AbortController + \n\n parser)
│   ├── useConfirm.tsx               # Confirmation dialog hook (built on AlertDialog)
│   └── useVersionCheck.ts           # Version update detection
│
├── pages/                   # Route components
│   ├── Overview.tsx         # Server dashboard
│   ├── Login.tsx            # Dual authentication
│   ├── Home.tsx             # Landing page
│   ├── Snapshots.tsx        # Global snapshots with deletion and unlock
│   ├── ArchiveManagement.tsx # Archive management
│   ├── CronManagement.tsx    # Cron jobs
│   ├── DnsManagement.tsx     # DNS records
│   ├── DynamicConfig.tsx     # Dynamic configuration
│   ├── PlayerManagement.tsx  # Player management
│   ├── admin/
│   │   └── UserManagement.tsx
│   ├── templates/
│   │   ├── TemplateList.tsx   # Template list with create/edit/copy/delete
│   │   ├── TemplateEdit.tsx   # Template editor (create/edit/copy-from modes)
│   │   └── DefaultVariables.tsx # Default variable configuration
│   └── server/
│       ├── ServerNew.tsx    # Server creation (template + traditional modes)
│       └── servers/
│           ├── ServerDetail.tsx    # Server overview
│           ├── ServerFiles.tsx     # File management with search
│           ├── ServerCompose.tsx   # Compose editing (auto-detects template/direct mode)
│           ├── ServerConsole.tsx   # Real-time terminal with xterm.js
│           └── ServerWorldRestore.tsx # World restore page (map + side panel + URL-driven dim/mode)
│
├── stores/                  # Zustand stores
│   ├── useTokenStore.ts           # JWT token
│   ├── useSidebarStore.ts         # Navigation state
│   ├── useLoginPreferenceStore.ts # Auth method preference
│   ├── useDownloadStore.ts        # Download tasks
│   ├── useBackgroundTaskStore.ts  # Background task state
│   ├── useTaskCenterStore.ts      # Task center panel state
│   └── useWorldRestoreSelectionStore.ts # Per-server world-restore selection (mode, dimension, chunk set; not persisted)

├── types/                   # TypeScript definitions
│   ├── Server.ts
│   ├── ServerInfo.ts
│   ├── ServerRuntime.ts
│   ├── MenuItem.ts
│   ├── User.ts
│   ├── Dns.ts
│   ├── MapTypes.ts          # Region manifest, chunk key, selection mode types
│   ├── lifecycle.ts         # Mirrors backend CreateServerResult / RemoveServerResult / SyncResult
│   └── WorldRestore.ts      # Pydantic-mirroring types for layout, restoration history, RestoreEvent / PreviewEvent SSE payloads

├── utils/                   # Utilities
│   ├── api.ts               # Axios config, query keys, interceptors
│   ├── serverUtils.ts       # Server state utilities
│   ├── devLogger.ts         # Development logging
│   ├── fileLanguageDetector.ts # File type detection
│   ├── fileSearchUtils.ts   # File search utilities
│   ├── formatUtils.ts       # UUID formatting, natural sorting
│   ├── downloadUtils.ts     # Download management
│   └── issueParser.tsx      # GitHub issue link parsing

├── config/
│   ├── fileEditingConfig.ts # File editing configuration
│   ├── versionConfig.ts     # Version management (current: v2.0.0)
│   ├── snbtLanguage.ts      # SNBT language config for Monaco
│   └── serverAddressConfig.ts # Server address mapping

├── public/static/
│   └── mc-server-compose-schema.json # Docker Compose schema for docker-minecraft-server

└── index.css                # Tailwind directives
```

## Three-Layer Data Architecture

**Layer 1: API Layer** (`hooks/api/`)
Raw Axios-based API functions with type safety. No caching, no side effects.

```typescript
// Example: playerApi.ts
export const fetchPlayers = async (serverId: string) => {
  const response = await api.get(`/servers/${serverId}/players`);
  return response.data;
};
```

**Layer 2: Base Query Layer** (`hooks/queries/base/`)
Resource-focused React Query hooks with caching strategies.

```typescript
// Example: usePlayerQueries.ts
export const usePlayerQueries = (serverId: string) => {
  return useQuery({
    queryKey: ["players", serverId],
    queryFn: () => fetchPlayers(serverId),
    refetchInterval: 30000, // 30s for real-time updates
  });
};
```

**Layer 3: Page Query Layer** (`hooks/queries/page/`)
Composed queries for page-specific data requirements.

```typescript
// Example: useServerDetailQueries.ts
export const useServerDetailQueries = (serverId: string) => {
  const { data: serverInfo } = useServerQueries(serverId);
  const { data: players } = usePlayerQueries(serverId);
  // Compose multiple queries for the page
  return { serverInfo, players };
};
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

### Background Task Center

**Unified task management UI** for long-running backend operations:

- Fixed Button trigger with active task badge count
- Card panel with tabs: Background Tasks + Downloads
- Real-time polling (1s when active, 10s otherwise)
- Task cancellation and removal
- Progress display with percentage and messages
- Auto-completion detection with cache invalidation

**Components:**

- `TaskCenterTrigger.tsx`: Fixed-position Button with badge and tooltip
- `TaskCenterPanel.tsx`: Floating Card with shadcn Tabs
- `BackgroundTaskList.tsx`: Task list with grouping
- `BackgroundTaskItem.tsx`: Individual task display with Popover details

**Hooks:**

- `useTaskQueries`: React Query hooks with smart polling
- `taskApi`: Backend API functions

**Stores:**

- `useBackgroundTaskStore`: Task state (persisted)
- `useTaskCenterStore`: Panel open/tab state

See `.claude/background-tasks-guide.md` for implementation guide.

### Bundled Lifecycle Requests

Server creation and removal each issue exactly **one** request to the
backend:

- `useCreateServer` posts `{ yaml_content | template_id+variable_values,
  restart_schedule? }` to `POST /servers/{id}` and returns
  `CreateServerResult`. Populate (archive extraction) remains a separate
  follow-up request because it runs as a background task.
- `useServerOperation({ action: "remove" })` posts to
  `POST /servers/{id}/operations` and returns `RemoveServerResult`; the
  backend bundles cron cancellation, session closure, log monitor stop,
  rmtree, and DNS update into the same call.
- `useSyncServers` powers `SyncWithFilesystemDialog`. It calls
  `POST /servers/sync` with `{ dry_run: true }` to populate the preview,
  then `{ dry_run: false }` to apply. On a 409 from the empty-filesystem
  guard, the dialog offers a "强制应用" button that retries with
  `{ force: true }`. OWNER-only — the trigger button in `Overview.tsx` is
  gated by `useCurrentUser().role === UserRole.OWNER`.

Type definitions live in `types/lifecycle.ts` (mirrors the backend's
Pydantic models).

### Server Template System

**Template-based server creation and management:**

The server creation page (`ServerNew.tsx`) supports two modes — **template mode** (select a template, fill variable form, auto-render YAML) and **traditional mode** (paste/edit Docker Compose YAML directly). The compose editing page (`ServerCompose.tsx`) auto-detects the server's mode and renders either `TemplateMode` or `DirectMode` accordingly.

**Template Management Pages:**

- `TemplateList.tsx`: Template table with create, edit, copy, delete actions
- `TemplateEdit.tsx`: Full template editor with YAML editor tab, variable definition form tab, and diff preview. Supports create/edit/copy-from modes.
- `DefaultVariables.tsx`: Configure default variables pre-filled when creating new templates

**Mode Conversion:**

`ConvertModeModal.tsx` is a multi-step wizard supporting:

- **Template → Direct**: One-step confirmation, no rebuild needed
- **Direct → Template**: 3-step flow (select template → extract/adjust variables → preview diff and confirm)
- **Template Update**: Apply template updates to an existing template-based server

The wizard uses `useExtractVariables` to infer variable values from the current compose by matching it against the template pattern, `useCheckConversion` to determine if a rebuild is needed, and `RebuildProgressModal` to track rebuild progress.

**Key Components:**

- `TemplateCreationMode` / `TraditionalCreationMode`: Server creation sub-pages
- `TemplateMode` / `DirectMode`: Compose editing sub-pages
- `ComposeDiffModal`: Monaco diff editor for YAML comparison
- `VariableDefinitionForm`: Visual editor for template variable definitions
- `SchemaForm` (rjsf): Renders variable input forms from JSON Schema generated by backend

### Version Update System

**Automatic version detection** with notifications:

- Version comparison and update detection
- Update modal with detailed changelog
- GitHub issue link parsing for clickable references
- "Remind later" functionality (1-hour delay)
- localStorage persistence for last seen version

## State Management

### Zustand Stores

**useTokenStore**:

```typescript
interface TokenStore {
  token: string | null;
  setToken: (token: string | null) => void;
  clearToken: () => void;
}
```

**useDownloadStore**:

```typescript
interface DownloadStore {
  tasks: DownloadTask[];
  addTask: (task: DownloadTask) => void;
  updateTask: (id: string, updates: Partial<DownloadTask>) => void;
  removeTask: (id: string) => void;
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
const { isConnected, sendMessage } = useServerConsoleWebSocket(
  serverId,
  onMessage,
);
```

Features:

- Direct container attach via docker-py backend
- xterm.js terminal emulation
- Real-time bidirectional communication
- Supports terminal features (command history, tab completion via MC server)
- Auto-reconnection handling
- Server-provided terminal features (history navigation, tab completion)

## Server Map (mcmap)

The map is no longer a standalone page — it's an embeddable component used exclusively by the world-restore page.

**Components:**

- `components/map/ServerMap.tsx` — Leaflet wrapper with `regionPath`, `regions` (manifest set), `initialView`/`onViewChange` (URL sync), `selectionMode` (`'none' | 'chunk' | 'region'`), controlled `selection` + `onSelectionChange`, `overlays` props. Interactions: plain left-drag pans; Ctrl + click adds the chunk/region under the cursor; Ctrl + drag adds a rectangle; right-click removes; right-button + drag subtracts; Escape (with the canvas focused) clears. Selection paint degrades to per-region rectangles past 5,000 chunks for performance.
- `components/map/ServerMapTileLayer.ts` — custom `L.GridLayer` that fetches PNGs through the project's authed `axios` instance (so the JWT applies), short-circuits to a blank tile for regions absent from the manifest, and aborts in-flight requests via `AbortController` when leaflet unloads tiles
- `components/map/coords.ts` — pure-function block ↔ chunk ↔ region conversions; also exposes `regionToChunkKeys`, `chunksToFullyCoveredRegions`, `chunksToCoveredRegions` for the world-restore mode-switch math and overlay rendering
- `components/map/MapHelpButton.tsx` — circular help button + dialog explaining the gesture model; mounted in the 地图回档 page header
- `components/dialogs/MapInitDialog.tsx` — two-stage progress dialog driven by SSE from `POST /servers/{id}/map/initialize`; opened from the 地图回档 page when the client JAR or palette is missing/stale, plus a "重载渲染前置" button once initialized

**Data flow:**

- `hooks/api/mapApi.ts` — REST: `getStatus(serverId)`, `getRegions(serverId, region)`
- `hooks/queries/base/useMapQueries.ts` — `useMapStatus`, `useMapRegions`
- The 地图回档 page gates tile rendering on `useMapStatus` (`client_jar_present && palette_present && palette_current`); when missing, the page shows the init prompt instead of the map

**Sparse-world optimization:** `GET /servers/{id}/map/regions?region=...` returns the list of `[x, z]` pairs that exist on disk for the selected dimension. The frontend turns it into a `Set<"x,z">` and passes it to the tile layer, which skips HTTP requests for any tile not in the set. The backend 404 path stays as a safety net for regions generated after the manifest was fetched.

**Cancellation cascade:** leaflet `_removeTile` → `AbortController.abort()` → axios cancels → backend handler `CancelledError` → queue refcount drop → mid-batch mcmap subprocess termination if last consumer leaves the active batch.

## World Restore Page

**Pages & Components:**

- `pages/server/servers/ServerWorldRestore.tsx` — page shell. URL is the source of truth for `?dim=<region_dir_relpath>&mode=region|chunk` plus `?z`, `?cx`, `?cz` for map view. Auto-selects the first world root's Overworld dimension when no URL params are present. The relpath alone identifies a (root, dim) pair because the root directory name is its first path segment, so multi-world setups are unambiguous without a separate root parameter. Embeds `<ServerMap>` on the left and `<WorldRestoreSelectionPanel>` on the right with `<ServerStopGuard>` above and `<ServerStartHint>` below.
- `components/world-restore/WorldRestoreSelectionPanel.tsx` — side panel with mode tabs (区域/区块), selection summary (chunks, covered regions, fully-covered regions), three "create snapshot" actions (selected scope / dimension / world), three "restore…" actions that open the snapshot picker, and a "view restore history" button. Mode-switch math runs through `chunksToFullyCoveredRegions`; demotion to region mode prompts a confirm if it would drop partially-covered regions.
- `components/world-restore/SnapshotPicker.tsx` — right-anchored `<Sheet>` listing eligible snapshots from `useEligibleSnapshots`. Each row offers Preview (opens `<RestorePreviewModal>`) and Restore (opens a destructive confirm, then drives the restore SSE via `useEventStream<RestoreEvent>` and renders progress in-place via `<RestoreProgressCard>`).
- `components/world-restore/RestorePreviewModal.tsx` — `<Dialog>` containing a mini Leaflet map with `CRS.Simple` and `<PreviewTileLayer>` (a clone of `ServerMapTileLayer` pointed at the preview tile endpoint). Drives `POST /preview` via `useEventStream<PreviewEvent>`, captures `session_id` from the `ready` event, heartbeats every 30s, and fires `DELETE /preview/{session_id}` on close.
- `components/world-restore/RestorationHistoryDrawer.tsx` — right-anchored `<Sheet>` listing rows from `useRestorations` (auto-refreshes every 5s). Per-row rollback gated on `status ∈ {succeeded, interrupted}` AND `safety_snapshot_id` set AND `is_rollback === false`. The "needs rollback" alert highlights `interrupted` rows.
- `components/world-restore/ServerStopGuard.tsx` — banner shown when status is anything but stopped/created/removed; offers a one-click confirm-and-stop. Backend re-checks inside the lock (returns 409) but the pre-flight nudge is friendlier. Companion `<ServerStartHint>` invites the user to start the server again post-restore.
- `components/world-restore/RestoreProgressCard.tsx` + `restoreProgress.ts` — shared SSE event reducer (`applyRestoreEvent`) and progress card UI used by both the snapshot picker (restore flow) and the history drawer (rollback flow).
- `components/world-restore/PreviewTileLayer.ts` — Leaflet `GridLayer` for the preview map; mirrors `ServerMapTileLayer` but hits `/preview/{session_id}/tile/{rx}/{rz}.png` and gates by an `available` set so empty regions don't 404.
- `components/world-restore/selectionUtils.ts` — `buildSelection(...)` packages the panel's state into the backend `RestorationSelection` shape; `computeSelectionStats(...)` returns chunk count, covered region count, fully-covered region count.

**Selection state** (`stores/useWorldRestoreSelectionStore.ts`):

- Per-server entries keyed by `serverId`, not persisted (selection is transient and intentionally clears on reload).
- `setMode` does the chunk → region collapse via `chunksToFullyCoveredRegions`; region → chunk is a no-op on the data (the underlying set is already chunks).
- `setDimension(serverId, dimension)` clears the selection when `dimension` changes — chunks aren't comparable across dimensions, and the dimension relpath uniquely identifies the (root, dim) pair on its own.

**SSE consumer** (`hooks/useEventStream.ts`):

- Generic `useEventStream<TEvent>({ enabled, url, method, body, onEvent, onClose, onError, onResponse })` — fetch + `AbortController` + `\n\n` block parser. Authorization header injected from `useTokenStore`. Body fingerprinting via `JSON.stringify` so caller-side inline objects don't restart the stream every render.
- Used for all three world-restore SSE flows: `POST /preview`, `POST /restore`, and `POST /restorations/{id}/rollback`.

**Routing & navigation:**

- Route: `<Route path=":id/world-restore" element={<ServerWorldRestore />} />` in `App.tsx`, lazy-loaded.
- Sidebar: `Map` lucide icon labeled "地图回档" under each server's submenu, navigating to `/server/{id}/world-restore`.

## Monaco Editor Integration

**Setup:**

- YAML worker: `yaml.worker.js`
- SNBT language: `snbtLanguage.ts` (custom language definition)
- Docker Compose schema validation with docker-minecraft-server specific hints
- Syntax highlighting for server files

**File Type Support:**

- YAML (Docker Compose with schema)
- JSON, JavaScript, TypeScript
- Python, Java, Shell scripts
- Properties files
- **SNBT** (Minecraft NBT format)

## Caching & Query Management

**Core Responsibility Split:**

- **API layer** (`hooks/api/`): transport only (Axios calls, typing, upload/download progress). No cache logic.
- **Query layer** (`hooks/queries/base/`, `hooks/queries/page/`): server-state reads, polling, stale-time strategy, and cache ownership.
- **Mutation layer** (`hooks/mutations/`): all write/command operations plus cache invalidation on success.

**When to Use Which:**

- Use **`useQuery` / `useQueries`** for reusable server state shared by pages/components.
- Use **`useMutation`** for create/update/delete/operation endpoints (including command-style APIs like start/stop/restart).
- Use **direct API calls** only for one-off, flow-local requests that should not be globally cached (for example modal-only preview/check calls) or stream/progress operations (download/upload).

**Query Key Rules (Mandatory):**

- Always use key factories from `utils/api.ts` (`queryKeys.*`), never inline string literals.
- Keep key hierarchy stable: `all` -> `list/detail/sub-resource`.
- Query hooks and invalidation must reference the same factory path.
- Prefer prefix invalidation via stable parents (for example `queryKeys.snapshots.all`) when affected fanout is broad.

**Invalidation Rules:**

- **Single-resource update**: invalidate that resource detail key.
- **List membership / aggregate changed**: invalidate related list and summary keys.
- **Cross-domain side effects**: also invalidate dependent domains (examples: DNS, restart schedule, players, snapshot repository usage).
- Prefer `invalidateQueries` for normal flows; use `refetchQueries` only for explicit user-triggered "refresh now" actions.

**Task-Driven Operations (Important):**

- For async backend tasks (rebuild/populate/template conversion), do not immediately invalidate business queries after task submission.
- Submit mutation -> invalidate task queries (`taskQueryKeys`) -> poll task detail.
- After task reaches `completed`, invalidate affected business keys in one place (progress modal completion handler).

**Volatility-Based Defaults:**

- **Fast-changing** (status/runtime/online players): short stale time + polling (seconds-level).
- **Moderate-changing** (disk usage, task lists): medium polling window.
- **Slow/static** (template schema, module schema, compose metadata): long stale time, mostly manual refresh/invalidation on mutation.

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
- shadcn/ui: `/shadcn-ui/ui`
- base-ui primitives: `/mui/base-ui`
- Tailwind CSS: `/tailwindlabs/tailwindcss`
- Lucide icons: `/lucide-icons/lucide`
- TanStack Query: `/tanstack/query`
- TanStack Table: `/tanstack/table`
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

## UI Stack Conventions (shadcn/ui + base-ui)

The frontend uses shadcn/ui components built on top of `@base-ui/react` primitives. A few project-specific conventions to remember:

- **Not Radix** — shadcn here uses base-ui, so patterns like `asChild` do **not** apply. Instead, use the `render` prop that base-ui's `useRender` accepts, or compose via controlled state.
- **TooltipProvider** is mounted once in `src/main.tsx`. Do **not** wrap individual components in another `TooltipProvider`.
- **Select** (`@/components/ui/select`) requires string `value`/`onValueChange`. When the display text differs from the option value (e.g. "10条/页" for value `"10"`), pass `itemToStringLabel={(v) => "..."}` on the `Select` so that the trigger renders the label correctly.
- **Toast** notifications use `sonner` (`import { toast } from 'sonner'`).
- **Confirmation dialogs** use the `useConfirm` hook (`hooks/useConfirm.ts`). It accepts `title`, `description`, `confirmText`, `cancelText`, `variant`, and `onConfirm` — it does **not** accept a `content` field. For rich confirmations (with diff previews etc.), use a dedicated state-driven `<Dialog>` instead.
- **Sidebar layout**: `MainLayout.tsx` wraps the app in `SidebarProvider` + `AppSidebar` + `SidebarInset`. `AppSidebar` uses `collapsible="icon"` mode with controlled `Collapsible` sections keyed by `useSidebarStore.openKeys`.

Legacy Ant Design has been fully removed (no `antd`, `@ant-design/icons`, or `@rjsf/antd` dependencies). The historical migration plan lives in `.claude/migration/` for reference only.
