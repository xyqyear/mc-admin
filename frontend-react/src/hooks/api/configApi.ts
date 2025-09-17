import api from '@/utils/api'

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

export interface SuccessResponse {
  success: boolean
  message: string
}

/**
 * List all registered configuration modules with their schema information
 */
export const listAllModules = async (): Promise<ConfigModuleList> => {
  const response = await api.get('/config/modules')
  return response.data
}

/**
 * Get configuration data for a specific module
 */
export const getModuleConfig = async (moduleName: string): Promise<ConfigData> => {
  const response = await api.get(`/config/modules/${moduleName}`)
  return response.data
}

/**
 * Update configuration for a specific module
 */
export const updateModuleConfig = async (
  moduleName: string,
  configData: Record<string, any>
): Promise<ConfigUpdateResponse> => {
  const response = await api.put(`/config/modules/${moduleName}`, {
    config_data: configData
  })
  return response.data
}

/**
 * Get schema information for a specific module
 */
export const getModuleSchema = async (moduleName: string): Promise<ConfigModuleInfo> => {
  const response = await api.get(`/config/modules/${moduleName}/schema`)
  return response.data
}

/**
 * Reset configuration for a module to default values
 */
export const resetModuleConfig = async (moduleName: string): Promise<ConfigUpdateResponse> => {
  const response = await api.post(`/config/modules/${moduleName}/reset`)
  return response.data
}

/**
 * Health check endpoint for the dynamic configuration system
 */
export const configHealthCheck = async (): Promise<SuccessResponse> => {
  const response = await api.get('/config/health')
  return response.data
}