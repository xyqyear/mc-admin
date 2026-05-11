/**
 * Shared types for the server lifecycle module.
 * Mirrors the Pydantic models in app/servers/lifecycle/types.py.
 */

export interface RestartScheduleRequest {
  custom_cron?: string | null;
}

export interface CreateServerRequest {
  yaml_content?: string;
  template_id?: number;
  variable_values?: Record<string, unknown>;
  restart_schedule?: RestartScheduleRequest | null;
}

export interface CreateServerResult {
  server_id: string;
  game_port: number;
  rcon_port: number;
  restart_cronjob_id: string | null;
}

export interface RemoveServerResult {
  server_id: string;
  cancelled_restart_cronjob_ids: string[];
  cancelled_background_task_ids: string[];
  closed_sessions: number;
}

export interface SyncEntryError {
  server_id: string;
  stage: "validate" | "adopt" | "deactivate";
  error: string;
}

export interface SyncDryRunEntry {
  server_id: string;
  action: "adopt" | "deactivate";
  game_port?: number | null;
  rcon_port?: number | null;
  restart_cronjob_count?: number | null;
  open_session_count?: number | null;
}

export interface SyncResult {
  applied: boolean;
  adopted: CreateServerResult[];
  removed: RemoveServerResult[];
  preview: SyncDryRunEntry[];
  errors: SyncEntryError[];
}

export interface SyncRequest {
  dry_run?: boolean;
  force?: boolean;
}
