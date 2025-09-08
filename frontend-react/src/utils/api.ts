import { useTokenStore } from "@/stores/useTokenStore";
import axios, { AxiosError, AxiosResponse } from "axios";

// Types for better error handling
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

/**
 * 获取API基础URL，支持相对路径和协议转换
 * @param ws 是否为WebSocket URL，如果为true则将http替换为ws，https替换为wss
 * @returns 处理后的完整URL
 */
export const getApiBaseUrl = (ws: boolean = false): string => {
  let baseUrl = window.location.origin + "/api"

  if (ws) {
    baseUrl = baseUrl
      .replace(/^https:/, 'wss:')
      .replace(/^http:/, 'ws:');
  }
  
  return baseUrl;
};

// Create axios instance with better defaults
export const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 60000, // Increased timeout for larger operations
  headers: {
    "Content-Type": "application/json",
  },
});

// Token management with better error handling
const getAuthToken = () => {
  try {
    return useTokenStore.getState().token;
  } catch (error) {
    console.error("Failed to get auth token:", error);
    return null;
  }
};

// Request interceptor with improved auth handling
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

// Response interceptor with comprehensive error handling
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    const status = error.response?.status;

    // Handle different error types
    if (status === 401) {
      // Clear token and let the app handle redirect through router
      try {
        useTokenStore.getState().clearToken();
      } catch (e) {
        console.error("Failed to clear token:", e);
      }
    }

    // Create standardized error object
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

// Utility function for sleep (useful for demos/testing)
export const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

// Query key factory for consistent cache keys
export const queryKeys = {
  // 系统级别
  system: {
    all: ["system"] as const,
    info: () => [...queryKeys.system.all, "info"] as const,
    diskUsage: () => [...queryKeys.system.all, "disk-usage"] as const,
  },

  // 服务器配置 (相对静态，长缓存)
  serverInfos: {
    all: ["serverInfos"] as const,
    lists: () => [...queryKeys.serverInfos.all, "list"] as const,
    detail: (id: string) =>
      [...queryKeys.serverInfos.all, "detail", id] as const,
  },

  // 服务器运行时 (动态，短缓存)
  serverRuntimes: {
    all: ["serverRuntimes"] as const,
    detail: (id: string) =>
      [...queryKeys.serverRuntimes.all, "detail", id] as const,
  },

  // 服务器状态 (中等频率更新)
  serverStatuses: {
    all: ["serverStatuses"] as const,
    detail: (id: string) =>
      [...queryKeys.serverStatuses.all, "detail", id] as const,
  },

  // 服务器磁盘使用情况 (始终可用)
  serverDiskUsage: {
    all: ["serverDiskUsage"] as const,
    detail: (id: string) =>
      [...queryKeys.serverDiskUsage.all, "detail", id] as const,
  },

  // 玩家相关 (仅健康状态时有效)
  players: {
    all: ["players"] as const,
    online: (id: string) => [...queryKeys.players.all, "online", id] as const,
  },

  // Compose文件
  compose: {
    all: ["compose"] as const,
    detail: (id: string) => [...queryKeys.compose.all, "detail", id] as const,
    file: (id: string) => [...queryKeys.compose.all, "file", id] as const,
  },

  // 文件管理
  files: {
    all: ["files"] as const,
    lists: (serverId: string) => [...queryKeys.files.all, serverId] as const,
    list: (serverId: string, path: string) =>
      [...queryKeys.files.all, serverId, path] as const,
    content: (serverId: string, path: string) =>
      [...queryKeys.files.all, serverId, "content", path] as const,
  },

  // 用户管理
  user: {
    all: ["user"] as const,
    me: () => [...queryKeys.user.all, "me"] as const,
  },

  // 管理员功能
  admin: {
    all: ["admin"] as const,
    users: () => [...queryKeys.admin.all, "users"] as const,
  },

  // 兼容现有代码
  all: ["api"] as const,
  servers: () => [...queryKeys.all, "servers"] as const,
  server: (id: string) => [...queryKeys.servers(), id] as const,
  serverPlayers: (id: string) => [...queryKeys.server(id), "players"] as const,
  serverFiles: (id: string) => [...queryKeys.server(id), "files"] as const,
  overview: () => [...queryKeys.all, "overview"] as const,
  backups: () => [...queryKeys.all, "backups"] as const,

  // 快照管理
  snapshots: {
    all: ["snapshots"] as const,
    global: () => [...queryKeys.snapshots.all, "global"] as const,
    repositoryUsage: () => [...queryKeys.snapshots.all, "repository-usage"] as const,
    forPath: (serverId: string, path: string) => 
      [...queryKeys.snapshots.all, "path", serverId, path] as const,
  },

  // 压缩包管理
  archive: {
    all: ["archive"] as const,
    files: (path: string) => [...queryKeys.archive.all, "files", path] as const,
    content: (path: string) => [...queryKeys.archive.all, "content", path] as const,
    sha256: (path: string) => [...queryKeys.archive.all, "sha256", path] as const,
  },
} as const;

export default api;
