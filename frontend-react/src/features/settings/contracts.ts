export type DNSProvider =
  | { type: 'huawei'; domain: string; ak: string; sk: string; region: string }
  | { type: 'dnspod'; domain: string; id: string; key: string }

export interface ManualAddress {
  type: 'manual'
  name: string
  record_type: 'A' | 'AAAA' | 'CNAME'
  value: string
  port: number
}

export interface DNSSettings {
  enabled: boolean
  dns: DNSProvider
  managed_sub_domain: string
  mc_router_base_url: string
  dns_ttl: number
  addresses: ManualAddress[]
}

export interface SnapshotSettings {
  time_restriction: { enabled: boolean; before_seconds: number; after_seconds: number }
  world_restore: { preview_session_ttl_seconds: number; preview_janitor_interval_seconds: number; preview_avg_region_bytes: number }
  ignored_paths: string[]
}

export interface LogParserSettings {
  uuid_patterns: string[]
  join_pattern: string
  leave_pattern: string
  server_stop_pattern: string
  chat_pattern: string
  achievement_patterns: string[]
}

export interface PlayerSettings {
  heartbeat: { crash_threshold_minutes: number; heartbeat_interval_seconds: number }
  rcon_validation: { validation_interval_seconds: number }
  skin_fetcher: { request_timeout_seconds: number }
  query: { query_command: string; timeout: number }
  ignored_name_prefixes: string[]
}

export interface MapSettings {
  prune_preview_ttl_seconds: number
  batch_size: number
  thread_count: number
  request_timeout_seconds: number
  prune_default_threshold_seconds: number
}

export interface WorldSettings {
  region_stat_workers: number
  dimension_max_depth_from_world_root: number
  dimension_labels: Record<string, string>
}

export interface SelfCheckSettings {
  checks: {
    backup_restic_configured: boolean
    backup_restic_reachable: boolean
    backup_server_snapshot_coverage: boolean
    backup_server_snapshot_freshness: boolean
    storage_backup_repository_usage: boolean
    storage_server_directory_usage: boolean
    locks_python_restic_active: boolean
    locks_repo_restic_active: boolean
    dns_drift: boolean
    dependency_binaries: boolean
    log_monitor_active: boolean
    server_backup_mod_removed: boolean
    server_game_port_consistency: boolean
    files_permission_consistency: boolean
    server_filesystem_db_sync: boolean
  }
  snapshot_freshness_minutes: number
  backup_repository_usage_percent: number
  server_directory_usage_percent: number
  retention_runs_keep_days: number
  backup_mod_ids: string[]
  permission_scan_max_entries: number
  event_triggers: {
    after_server_created: boolean
    after_server_populated: boolean
    after_world_restored: boolean
    after_world_rolled_back: boolean
  }
}
