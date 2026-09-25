
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

export interface DefaultVariablesResponse {
  variable_definitions: VariableDefinition[];
}
