
export interface ConfigModuleInfo {
  module_name: string
  schema_class: string
  version: string
  json_schema: Record<string, any>
}

export interface ConfigModuleList {
  modules: Record<string, ConfigModuleInfo>
}

export interface ConfigData {
  module_name: string
  config_data: Record<string, any>
  schema_version: string
}

export interface ConfigUpdateRequest {
  config_data: Record<string, any>
}

export interface ConfigUpdateResponse {
  success: boolean
  message: string
  updated_config: Record<string, any>
}
