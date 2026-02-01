import { api } from "@/utils/api";

// Variable definition types
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

// Template types
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
  variables: VariableDefinition[];
  system_variables: VariableDefinition[];
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

// Request types
export interface TemplateCreateRequest {
  name: string;
  description?: string;
  yaml_template: string;
  variables: VariableDefinition[];
  copy_from_template_id?: number;
}

export interface TemplateUpdateRequest {
  name?: string;
  description?: string;
  yaml_template?: string;
  variables?: VariableDefinition[];
}

// Template config types (for template-created servers)
export interface TemplateConfigResponse {
  server_id: string;
  template_id: number;
  template_name: string;
  yaml_template: string;
  variables: VariableDefinition[];
  system_variables: VariableDefinition[];
  variable_values: Record<string, unknown>;
  json_schema: Record<string, unknown>;
  snapshot_time: string;
}

export interface TemplateConfigUpdateResponse {
  task_id: string;
}

export interface TemplateConfigPreviewResponse {
  is_template_based: boolean;
  template_id: number | null;
}

export const templateApi = {
  // List all templates
  getTemplates: async (): Promise<TemplateListItem[]> => {
    const res = await api.get<TemplateListItem[]>("/templates/");
    return res.data;
  },

  // Get template details
  getTemplate: async (id: number): Promise<Template> => {
    const res = await api.get<Template>(`/templates/${id}`);
    return res.data;
  },

  // Create a new template
  createTemplate: async (request: TemplateCreateRequest): Promise<Template> => {
    const res = await api.post<Template>("/templates/", request);
    return res.data;
  },

  // Update an existing template
  updateTemplate: async (
    id: number,
    request: TemplateUpdateRequest
  ): Promise<Template> => {
    const res = await api.put<Template>(`/templates/${id}`, request);
    return res.data;
  },

  // Delete a template
  deleteTemplate: async (id: number): Promise<void> => {
    await api.delete(`/templates/${id}`);
  },

  // Get JSON Schema for template variables
  getTemplateSchema: async (id: number): Promise<TemplateSchema> => {
    const res = await api.get<TemplateSchema>(`/templates/${id}/schema`);
    return res.data;
  },

  // Get available ports for new server
  getAvailablePorts: async (): Promise<AvailablePorts> => {
    const res = await api.get<AvailablePorts>("/templates/ports/available");
    return res.data;
  },

  // Get system reserved variables
  getSystemVariables: async (): Promise<VariableDefinition[]> => {
    const res = await api.get<VariableDefinition[]>("/templates/system-variables");
    return res.data;
  },

  // Preview rendered YAML
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

  // Check if server is template-based
  getServerTemplatePreview: async (
    serverId: string
  ): Promise<TemplateConfigPreviewResponse> => {
    const res = await api.get<TemplateConfigPreviewResponse>(
      `/servers/${serverId}/template-config/preview`
    );
    return res.data;
  },

  // Get template config for a template-created server
  getServerTemplateConfig: async (
    serverId: string
  ): Promise<TemplateConfigResponse> => {
    const res = await api.get<TemplateConfigResponse>(
      `/servers/${serverId}/template-config`
    );
    return res.data;
  },

  // Update template config for a template-created server (returns task_id for tracking rebuild progress)
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
};

// Export types
export type {
  TemplateListItem as TemplateListItemType,
  Template as TemplateType,
  TemplateSchema as TemplateSchemaType,
};
