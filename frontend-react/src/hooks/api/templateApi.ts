import { api } from "@/utils/api";

export type VariableType = "int" | "float" | "string" | "enum" | "bool";

export interface IntVariableDefinition {
  type: "int";
  name: string;
  display_name: string;
  description?: string;
  default?: number;
  min_value?: number;
  max_value?: number;
}

export interface FloatVariableDefinition {
  type: "float";
  name: string;
  display_name: string;
  description?: string;
  default?: number;
  min_value?: number;
  max_value?: number;
}

export interface StringVariableDefinition {
  type: "string";
  name: string;
  display_name: string;
  description?: string;
  default?: string;
  max_length?: number;
  pattern?: string;
}

export interface EnumVariableDefinition {
  type: "enum";
  name: string;
  display_name: string;
  description?: string;
  default?: string;
  options: string[];
}

export interface BoolVariableDefinition {
  type: "bool";
  name: string;
  display_name: string;
  description?: string;
  default?: boolean;
}

export type VariableDefinition =
  | IntVariableDefinition
  | FloatVariableDefinition
  | StringVariableDefinition
  | EnumVariableDefinition
  | BoolVariableDefinition;

export interface TemplateListItem {
  id: number;
  name: string;
  description?: string;
  variable_count: number;
  created_at: string;
}

export interface Template {
  id: number;
  name: string;
  description?: string;
  yaml_template: string;
  variable_definitions: VariableDefinition[];
  created_at: string;
  updated_at: string;
}

export interface TemplateSchema {
  template_id: number;
  template_name: string;
  json_schema: Record<string, unknown>;
}

export interface AvailablePorts {
  suggested_game_port: number;
  suggested_rcon_port: number;
  used_ports: number[];
}

export interface TemplateCreateRequest {
  name: string;
  description?: string;
  yaml_template: string;
  variable_definitions: VariableDefinition[];
}

export interface TemplateUpdateRequest {
  name?: string;
  description?: string;
  yaml_template?: string;
  variable_definitions?: VariableDefinition[];
}

export interface TemplateConfigResponse {
  server_id: string;
  template_id: number;
  template_name: string;
  yaml_template: string;
  variable_definitions: VariableDefinition[];
  variable_values: Record<string, unknown>;
  json_schema: Record<string, unknown>;
  snapshot_time: string;
  has_template_update: boolean;
  template_deleted: boolean;
}

export interface TemplateConfigUpdateResponse {
  task_id: string;
}

export interface TemplateConfigPreviewResponse {
  is_template_based: boolean;
  template_id: number | null;
}

export interface DefaultVariablesResponse {
  variable_definitions: VariableDefinition[];
}

export interface ConvertToDirectResponse {
  success: boolean;
}

export interface ExtractVariablesResponse {
  extracted_values: Record<string, unknown>;
  warnings: string[];
  json_schema: Record<string, unknown>;
  variable_definitions: VariableDefinition[];
  current_compose: string;
  rendered_compose: string;
}

export interface ConvertToTemplateResponse {
  task_id: string | null;
  skipped_rebuild: boolean;
}

export interface CheckConversionRequest {
  template_id: number;
  variable_values: Record<string, unknown>;
}

export interface CheckConversionResponse {
  requires_rebuild: boolean;
}

export const templateApi = {
  getTemplates: async (): Promise<TemplateListItem[]> => {
    const res = await api.get<TemplateListItem[]>("/templates/");
    return res.data;
  },

  getTemplate: async (id: number): Promise<Template> => {
    const res = await api.get<Template>(`/templates/${id}`);
    return res.data;
  },

  createTemplate: async (request: TemplateCreateRequest): Promise<Template> => {
    const res = await api.post<Template>("/templates/", request);
    return res.data;
  },

  updateTemplate: async (
    id: number,
    request: TemplateUpdateRequest
  ): Promise<Template> => {
    const res = await api.put<Template>(`/templates/${id}`, request);
    return res.data;
  },

  deleteTemplate: async (id: number): Promise<void> => {
    await api.delete(`/templates/${id}`);
  },

  getTemplateSchema: async (id: number): Promise<TemplateSchema> => {
    const res = await api.get<TemplateSchema>(`/templates/${id}/schema`);
    return res.data;
  },

  getAvailablePorts: async (): Promise<AvailablePorts> => {
    const res = await api.get<AvailablePorts>("/templates/ports/available");
    return res.data;
  },

  previewRenderedYaml: async (
    id: number,
    variableValues: Record<string, unknown>
  ): Promise<string> => {
    const res = await api.post<{ rendered_yaml: string }>(
      `/templates/${id}/preview`,
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
    variableValues: Record<string, unknown>
  ): Promise<TemplateConfigUpdateResponse> => {
    const res = await api.put<TemplateConfigUpdateResponse>(
      `/servers/${serverId}/template-config`,
      { variable_values: variableValues }
    );
    return res.data;
  },

  getDefaultVariables: async (): Promise<DefaultVariablesResponse> => {
    const res = await api.get<DefaultVariablesResponse>(
      "/templates/default-variables"
    );
    return res.data;
  },

  updateDefaultVariables: async (
    variables: VariableDefinition[]
  ): Promise<DefaultVariablesResponse> => {
    const res = await api.put<DefaultVariablesResponse>(
      "/templates/default-variables",
      { variable_definitions: variables }
    );
    return res.data;
  },

  convertToDirectMode: async (
    serverId: string
  ): Promise<ConvertToDirectResponse> => {
    const res = await api.post<ConvertToDirectResponse>(
      `/servers/${serverId}/convert-to-direct`
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
    variableValues: Record<string, unknown>
  ): Promise<ConvertToTemplateResponse> => {
    const res = await api.post<ConvertToTemplateResponse>(
      `/servers/${serverId}/convert-to-template`,
      { template_id: templateId, variable_values: variableValues }
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
};

export type {
  TemplateListItem as TemplateListItemType,
  Template as TemplateType,
  TemplateSchema as TemplateSchemaType,
};
