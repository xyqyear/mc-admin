import type { SystemInfo, SystemDiskUsage } from "@/features/system/contracts";
import { api } from "@/shared/http/api";

export const systemApi = {
  getSystemInfo: async (): Promise<SystemInfo> => {
    const res = await api.get<SystemInfo>("/system/info");
    return res.data;
  },

  getSystemCpuPercent: async (): Promise<{ cpuPercentage: number }> => {
    const res = await api.get<{ cpuPercentage: number }>("/system/cpu_percent");
    return res.data;
  },

  getSystemDiskUsage: async (): Promise<SystemDiskUsage> => {
    const res = await api.get<SystemDiskUsage>("/system/disk-usage");
    return res.data;
  },
};
