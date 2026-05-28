import { useTokenStore } from "@/stores/useTokenStore";
import axios, { AxiosError, AxiosResponse } from "axios";

export interface ApiError {
  message: string;
  status?: number;
  code?: string;
}

export interface ApiResponse<T = any> {
  data: T;
  message?: string;
  success: boolean;
}

// When `ws` is true, swap http(s) for ws(s) so the same origin works for WebSocket URLs.
export const getApiBaseUrl = (ws: boolean = false): string => {
  let baseUrl = window.location.origin + "/api"

  if (ws) {
    baseUrl = baseUrl
      .replace(/^https:/, 'wss:')
      .replace(/^http:/, 'ws:');
  }

  return baseUrl;
};

export const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 60000,
  headers: {
    "Content-Type": "application/json",
  },
});

const getAuthToken = () => {
  try {
    return useTokenStore.getState().token;
  } catch (error) {
    console.error("Failed to get auth token:", error);
    return null;
  }
};

api.interceptors.request.use(
  (config) => {
    const token = getAuthToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => {
    console.error("Request interceptor error:", error);
    return Promise.reject(error);
  }
);

api.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    const status = error.response?.status;

    if (status === 401) {
      // Clear the token; the router-level auth wrapper handles the redirect.
      try {
        useTokenStore.getState().clearToken();
      } catch (e) {
        console.error("Failed to clear token:", e);
      }
    }

    const apiError: ApiError = {
      message:
        (error.response?.data as any)?.detail ||
        (error.response?.data as any)?.message ||
        error.message ||
        "Network error",
      status,
      code: error.code,
    };

    return Promise.reject(apiError);
  }
);

export const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

// Single source of truth for React Query cache keys. Hooks and invalidations
// must always reference these factories so prefix-invalidation works.
export const queryKeys = {
  system: {
    all: ["system"] as const,
    info: () => [...queryKeys.system.all, "info"] as const,
    cpuPercent: () => [...queryKeys.system.info(), "cpu"] as const,
    diskUsage: () => [...queryKeys.system.all, "disk-usage"] as const,
  },

  serverInfos: {
    all: ["serverInfos"] as const,
    detail: (id: string) =>
      [...queryKeys.serverInfos.all, "detail", id] as const,
  },

  serverRuntimes: {
    all: ["serverRuntimes"] as const,
    detail: (id: string) =>
      [...queryKeys.serverRuntimes.all, "detail", id] as const,
    cpu: (id: string) => [...queryKeys.serverRuntimes.detail(id), "cpu"] as const,
    memory: (id: string) =>
      [...queryKeys.serverRuntimes.detail(id), "memory"] as const,
    ioStats: (id: string) =>
      [...queryKeys.serverRuntimes.detail(id), "iostats"] as const,
    disk: (id: string) =>
      [...queryKeys.serverRuntimes.detail(id), "disk"] as const,
  },

  serverStatuses: {
    all: ["serverStatuses"] as const,
    detail: (id: string) =>
      [...queryKeys.serverStatuses.all, "detail", id] as const,
    batch: (ids: readonly string[]) =>
      [...queryKeys.serverStatuses.all, "batch", ids] as const,
  },

  players: {
    all: ["players"] as const,
    list: (filters?: { online_only?: boolean; server_id?: string }) =>
      [...queryKeys.players.all, "list", filters] as const,
    detailByUUID: (uuid: string) => [...queryKeys.players.all, "detail", "uuid", uuid] as const,
    cleanupPreview: (kind?: string | null) =>
      [...queryKeys.players.all, "cleanup", kind, "preview"] as const,
    mapProfileByUUID: (uuid: string) =>
      [...queryKeys.players.all, "map-profile", "uuid", uuid] as const,
    serverOnline: (serverId: string) => [...queryKeys.players.all, "server", serverId, "online"] as const,
    sessions: (playerDbId: number, params?: any) =>
      [...queryKeys.players.all, playerDbId, "sessions", params] as const,
    sessionStats: (playerDbId: number, period: string) =>
      [...queryKeys.players.all, playerDbId, "session-stats", period] as const,
    chat: (playerDbId: number, params?: any) =>
      [...queryKeys.players.all, playerDbId, "chat", params] as const,
    achievements: (playerDbId: number, serverId?: string) =>
      [...queryKeys.players.all, playerDbId, "achievements", serverId] as const,
  },

  compose: {
    all: ["compose"] as const,
    detail: (id: string) => [...queryKeys.compose.all, "detail", id] as const,
  },

  files: {
    all: ["files"] as const,
    lists: (serverId: string) => [...queryKeys.files.all, serverId] as const,
    list: (serverId: string, path: string) =>
      [...queryKeys.files.all, serverId, path] as const,
    content: (serverId: string, path: string) =>
      [...queryKeys.files.all, serverId, "content", path] as const,
  },

  user: {
    all: ["user"] as const,
    me: () => [...queryKeys.user.all, "me"] as const,
  },

  admin: {
    all: ["admin"] as const,
    users: () => [...queryKeys.admin.all, "users"] as const,
  },

  all: ["api"] as const,
  servers: () => [...queryKeys.all, "servers"] as const,

  snapshots: {
    all: ["snapshots"] as const,
    global: () => [...queryKeys.snapshots.all, "global"] as const,
    repositoryUsage: () => [...queryKeys.snapshots.all, "repository-usage"] as const,
    locks: () => [...queryKeys.snapshots.all, "locks"] as const,
    forPath: (serverId: string, path: string) =>
      [...queryKeys.snapshots.all, "path", serverId, path] as const,
  },

  archive: {
    all: ["archive"] as const,
    files: (path: string) => [...queryKeys.archive.all, "files", path] as const,
  },

  config: {
    all: ["config"] as const,
    modules: () => [...queryKeys.config.all, "modules"] as const,
    moduleConfig: (moduleName: string) => [...queryKeys.config.all, "module", moduleName] as const,
    moduleSchema: (moduleName: string) => [...queryKeys.config.all, "schema", moduleName] as const,
  },

  cron: {
    all: ["cron"] as const,
    list: (filters?: { identifier?: string; status?: string[] }) =>
      [...queryKeys.cron.all, "list", filters] as const,
    registeredTypes: () => [...queryKeys.cron.all, "registered"] as const,
    detail: (cronjobId: string) => [...queryKeys.cron.all, "detail", cronjobId] as const,
    executions: (cronjobId: string, limit?: number) =>
      [...queryKeys.cron.all, "executions", cronjobId, ...(limit ? [limit] : [])] as const,
    nextRunTime: (cronjobId: string) => [...queryKeys.cron.all, "next-run-time", cronjobId] as const,
  },

  restartSchedule: {
    all: ["restartSchedule"] as const,
    detail: (serverId: string) => [...queryKeys.restartSchedule.all, "detail", serverId] as const,
  },

  dns: {
    all: ["dns"] as const,
    status: () => [...queryKeys.dns.all, "status"] as const,
    enabled: () => [...queryKeys.dns.all, "enabled"] as const,
    records: () => [...queryKeys.dns.all, "records"] as const,
    routes: () => [...queryKeys.dns.all, "routes"] as const,
  },

  // mcmap init status + region manifest, consumed by the world-restore page.
  map: {
    all: ["map"] as const,
    status: (serverId: string) => [...queryKeys.map.all, "status", serverId] as const,
    regions: (serverId: string, region: string) =>
      [...queryKeys.map.all, "regions", serverId, region] as const,
  },

  worldRestore: {
    all: ["world-restore"] as const,
    layout: (serverId: string) =>
      [...queryKeys.worldRestore.all, "layout", serverId] as const,
    dimensionLabels: (serverId: string) =>
      [...queryKeys.worldRestore.all, "dimension-labels", serverId] as const,
    playerLocations: (serverId: string) =>
      [...queryKeys.worldRestore.all, "player-locations", serverId] as const,
    eligible: (serverId: string, selection: unknown) =>
      [...queryKeys.worldRestore.all, "eligible", serverId, selection] as const,
    history: (serverId: string) =>
      [...queryKeys.worldRestore.all, "history", serverId] as const,
    restoration: (serverId: string, id: string) =>
      [...queryKeys.worldRestore.all, "restoration", serverId, id] as const,
  },

  ftbClaims: {
    all: ["ftb-claims"] as const,
    claims: (serverId: string) =>
      [...queryKeys.ftbClaims.all, "claims", serverId] as const,
  },

  templates: {
    all: ["templates"] as const,
    list: () => [...queryKeys.templates.all, "list"] as const,
    detail: (id: number) => [...queryKeys.templates.all, "detail", id] as const,
    schema: (id: number) => [...queryKeys.templates.all, "schema", id] as const,
    availablePorts: () => [...queryKeys.templates.all, "available-ports"] as const,
    serverConfigs: () => [...queryKeys.templates.all, "server-config"] as const,
    serverConfig: (serverId: string) => [...queryKeys.templates.all, "server-config", serverId] as const,
    serverConfigPreview: (serverId: string) => [...queryKeys.templates.all, "server-config-preview", serverId] as const,
    defaultVariables: () => [...queryKeys.templates.all, "default-variables"] as const,
  },
} as const;

export default api;
