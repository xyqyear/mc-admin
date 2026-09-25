import type { RegistrationStatus } from '@/features/schedules/contracts'
// Mirrors MCServerInfo from minecraft-docker-manager-lib.
export interface ServerInfo {
  id: string;
  name: string;
  path: string;
  javaVersion: number;
  maxMemoryBytes: number;
  serverType: ServerType;
  gameVersion: string;
  gamePort: number;
  rconPort: number;
}

export type ServerType =
  | "VANILLA"
  | "PAPER"
  | "FORGE"
  | "NEOFORGE"
  | "FABRIC"
  | "SPIGOT"
  | "BUKKIT"
  | "CUSTOM";

export type ServerStatus =
  | "REMOVED"
  | "EXISTS"
  | "CREATED"
  | "RUNNING"
  | "STARTING"
  | "HEALTHY";

export interface ServerListItem {
  id: string;
  name: string;
  serverType: string;
  gameVersion: string;
  gamePort: number;
  maxMemoryBytes: number;
  rconPort: number;
  javaVersion: number;
}

export interface ServerStatusResponse {
  status: ServerStatus;
}

export interface ServerMaintenanceResponse {
  active: boolean;
  kind: string | null;
  description: string | null;
}

export interface ServerCpuPercentResponse {
  cpuPercentage: number;
}

export interface ServerMemoryResponse {
  memoryUsageBytes: number;
}

export interface ServerIOStatsResponse {
  diskReadBytes: number;
  diskWriteBytes: number;
  networkReceiveBytes: number;
  networkSendBytes: number;
}

export interface ServerDiskUsageResponse {
  diskUsageBytes: number;
  diskTotalBytes: number;
  diskAvailableBytes: number;
}

export interface ServerOperationRequest {
  action: string;
}

export interface RestartScheduleRequestBody {
  custom_cron?: string | null;
}

export interface CreateServerRequest {
  yaml_content?: string;
  template_id?: number;
  variable_values?: Record<string, unknown>;
  restart_schedule?: RestartScheduleRequestBody | null;
}

export interface PopulateServerRequest {
  archive_filename: string;
}

export interface PopulateServerResponse {
  task_id: string
}

export interface RestartScheduleResponse {
  registration_status?: RegistrationStatus
  registration_error?: string | null
  cronjob_id: string;
  server_id: string;
  name: string;
  cron: string;
  status: string;
  next_run_time: string | null;
  scheduled_time: string;
}
