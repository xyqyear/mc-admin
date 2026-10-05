import type { ServerStatus } from "@/features/servers/contracts";

export const serverStatusUtils = {
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
};
