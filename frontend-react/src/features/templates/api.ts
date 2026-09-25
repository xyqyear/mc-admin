import { api } from "@/shared/http/api";
import type { VariableDefinition, TemplateListItem, Template, TemplateSchema, AvailablePorts, TemplateCreateRequest, TemplateUpdateRequest, DefaultVariablesResponse } from '@/features/templates/contracts';


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


};