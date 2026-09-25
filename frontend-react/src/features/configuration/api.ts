import { api, type ApiError } from '@/shared/http/api'
import type { ComposeConfiguration, TemplateConfigResponse, TemplateConfigPreviewResponse, TemplateConfigUpdateResponse, ConvertToDirectResponse, ExtractVariablesResponse, ConvertToTemplateResponse, CheckConversionResponse } from '@/features/configuration/contracts'

function requireVersion(version: string): string {
  if (!version) throw new Error('配置版本缺失，请重新载入后再提交')
  return version
}

export function isConfigurationConflict(error: unknown): boolean {
  const detail = (error as ApiError | undefined)?.detail
  return !!detail && typeof detail === 'object' && 'code' in detail && detail.code === 'configuration_conflict'
}

export const configurationApi = {
  getCompose: async (serverId: string, signal?: AbortSignal): Promise<ComposeConfiguration> =>
    (await api.get<ComposeConfiguration>(`/servers/${serverId}/compose`, { signal })).data,
  updateCompose: async (serverId: string, yamlContent: string, expectedVersion: string): Promise<{task_id: string}> =>
    (await api.post<{task_id: string}>(`/servers/${serverId}/compose`, { yaml_content: yamlContent, expected_version: requireVersion(expectedVersion) })).data,
  previewServerTemplateConfig: async (
    serverId: string,
    variableValues: Record<string, unknown>
  ): Promise<string> => {
    const res = await api.post<{ rendered_yaml: string }>(
      `/servers/${serverId}/template-config/preview`,
      { variable_values: variableValues }
    );
    return res.data.rendered_yaml;
  },

  getServerTemplatePreview: async (
    serverId: string
  ): Promise<TemplateConfigPreviewResponse> => {
    const res = await api.get<TemplateConfigPreviewResponse>(
      `/servers/${serverId}/template-config/preview`
    );
    return res.data;
  },

  getServerTemplateConfig: async (
    serverId: string
  ): Promise<TemplateConfigResponse> => {
    const res = await api.get<TemplateConfigResponse>(
      `/servers/${serverId}/template-config`
    );
    return res.data;
  },

  // Returns a task_id; rebuild progress is polled via the task API.
  updateServerTemplateConfig: async (
    serverId: string,
    variableValues: Record<string, unknown>,
    expectedVersion: string
  ): Promise<TemplateConfigUpdateResponse> => {
    const res = await api.put<TemplateConfigUpdateResponse>(
      `/servers/${serverId}/template-config`,
      { variable_values: variableValues, expected_version: requireVersion(expectedVersion) }
    );
    return res.data;
  },

  convertToDirectMode: async (
    serverId: string,
    expectedVersion: string
  ): Promise<ConvertToDirectResponse> => {
    const res = await api.post<ConvertToDirectResponse>(
      `/servers/${serverId}/convert-to-direct`,
      { expected_version: requireVersion(expectedVersion) }
    );
    return res.data;
  },

  extractVariables: async (
    serverId: string,
    templateId: number
  ): Promise<ExtractVariablesResponse> => {
    const res = await api.post<ExtractVariablesResponse>(
      `/servers/${serverId}/extract-variables`,
      { template_id: templateId }
    );
    return res.data;
  },

  convertToTemplateMode: async (
    serverId: string,
    templateId: number,
    variableValues: Record<string, unknown>,
    expectedVersion: string
  ): Promise<ConvertToTemplateResponse> => {
    const res = await api.post<ConvertToTemplateResponse>(
      `/servers/${serverId}/convert-to-template`,
      { template_id: templateId, variable_values: variableValues, expected_version: requireVersion(expectedVersion) }
    );
    return res.data;
  },

  checkConversion: async (
    serverId: string,
    templateId: number,
    variableValues: Record<string, unknown>
  ): Promise<CheckConversionResponse> => {
    const res = await api.post<CheckConversionResponse>(
      `/servers/${serverId}/check-conversion`,
      { template_id: templateId, variable_values: variableValues }
    );
    return res.data;
  },
}
