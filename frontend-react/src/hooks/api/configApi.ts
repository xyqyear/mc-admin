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

export const listAllModules = async (): Promise<ConfigModuleList> => {
  const response = await api.get('/config/modules')
  return response.data
}

export const getModuleConfig = async (moduleName: string): Promise<ConfigData> => {
  const response = await api.get(`/config/modules/${moduleName}`)
  return response.data
}

export const updateModuleConfig = async (
  moduleName: string,
  configData: Record<string, any>
): Promise<ConfigUpdateResponse> => {
  const response = await api.put(`/config/modules/${moduleName}`, {
    config_data: configData
  })
  return response.data
}

export const getModuleSchema = async (moduleName: string): Promise<ConfigModuleInfo> => {
  const response = await api.get(`/config/modules/${moduleName}/schema`)
  return response.data
}

export const resetModuleConfig = async (moduleName: string): Promise<ConfigUpdateResponse> => {
  const response = await api.post(`/config/modules/${moduleName}/reset`)
  return response.data
}
