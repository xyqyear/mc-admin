import type { ServerStatus, ServerType } from "@/types/ServerInfo";

export const serverStatusUtils = {
  getStatusColor: (status: ServerStatus): string => {
    switch (status) {
      case "HEALTHY":
        return "success";
      case "RUNNING":
        return "processing";
      case "STARTING":
        return "warning";
      case "CREATED":
        return "default";
      case "EXISTS":
        return "warning";
      case "REMOVED":
        return "error";
      default:
        return "default";
    }
  },

  getStatusIcon: (status: ServerStatus): string => {
    switch (status) {
      case "HEALTHY":
        return "CheckCircleOutlined";
      case "RUNNING":
        return "PlayCircleOutlined";
      case "STARTING":
        return "LoadingOutlined";
      case "CREATED":
        return "PauseCircleOutlined";
      case "EXISTS":
        return "ExclamationCircleOutlined";
      case "REMOVED":
        return "MinusCircleOutlined";
      default:
        return "ExclamationCircleOutlined";
    }
  },

  isOperationAvailable: (operation: string, status: ServerStatus): boolean => {
    switch (operation) {
      case "start":
        return ["CREATED"].includes(status);
      case "up":
        return ["EXISTS"].includes(status);
      case "stop":
        return ["RUNNING", "HEALTHY", "STARTING"].includes(status);
      case "restart":
        return ["RUNNING", "HEALTHY", "STARTING"].includes(status);
      case "down":
        return ["CREATED", "RUNNING", "STARTING", "HEALTHY"].includes(status);
      case "remove":
        return ["EXISTS"].includes(status);
      default:
        return false;
    }
  },

  isRunning: (status: ServerStatus): boolean => {
    return ["RUNNING", "STARTING", "HEALTHY"].includes(status);
  },

  isHealthy: (status: ServerStatus): boolean => {
    return status === "HEALTHY";
  },
};

export const serverTypeUtils = {
  getTypeColor: (type: ServerType): string => {
    switch (type) {
      case "VANILLA":
        return "green";
      case "PAPER":
        return "blue";
      case "FORGE":
        return "orange";
      case "FABRIC":
        return "purple";
      case "SPIGOT":
        return "cyan";
      case "BUKKIT":
        return "gold";
      case "NEOFORGE":
        return "red";
      case "CUSTOM":
        return "default";
      default:
        return "default";
    }
  },
};

export const formatUtils = {
  formatBytes: (bytes: number, decimals: number = 1): string => {
    if (bytes === 0) return "0 B";

    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["B", "KB", "MB", "GB", "TB"];

    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
  },

  formatPercentage: (value: number, decimals: number = 1): string => {
    return `${value.toFixed(decimals)}%`;
  },

  formatMemoryMB: (bytes: number): string => {
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  },

  formatMemoryGB: (bytes: number): string => {
    return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
  },

  formatUptime: (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0) {
      return `${days}天 ${hours}小时`;
    } else if (hours > 0) {
      return `${hours}小时 ${minutes}分钟`;
    } else {
      return `${minutes}分钟`;
    }
  },
};

export const serverAddressUtils = {
  getConnectionAddress: (port: number, host: string = "localhost"): string => {
    return `${host}:${port}`;
  },

  copyServerAddress: async (
    port: number,
    host: string = "localhost"
  ): Promise<void> => {
    const address = serverAddressUtils.getConnectionAddress(port, host);
    await navigator.clipboard.writeText(address);
  },
};
