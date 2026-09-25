import type { VariableDefinition } from '@/features/templates/contracts';

export interface ComposeConfiguration { yaml_content: string; version: string }

export interface TemplateConfigResponse {
  version: string;
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

export interface ConvertToDirectResponse {
  success: boolean;
}

export interface ExtractVariablesResponse {
  version: string;
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
  version: string;
  requires_rebuild: boolean;
}
