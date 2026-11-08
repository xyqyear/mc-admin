

export interface IntVariableDefinition {
  type: "int";
  name: string;
  display_name: string;
  description?: string | null;
  default?: number | null;
  min_value?: number | null;
  max_value?: number | null;
}

export interface FloatVariableDefinition {
  type: "float";
  name: string;
  display_name: string;
  description?: string | null;
  default?: number | null;
  min_value?: number | null;
  max_value?: number | null;
}

export interface StringVariableDefinition {
  type: "string";
  name: string;
  display_name: string;
  description?: string | null;
  default?: string | null;
  max_length?: number | null;
  pattern?: string | null;
}

export interface EnumVariableDefinition {
  type: "enum";
  name: string;
  display_name: string;
  description?: string | null;
  default?: string | null;
  options: string[];
}

export interface BoolVariableDefinition {
  type: "bool";
  name: string;
  display_name: string;
  description?: string | null;
  default?: boolean | null;
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
  description?: string | null;
  variable_count: number;
  created_at: string;
}

export interface Template {
  id: number;
  name: string;
  description?: string | null;
  yaml_template: string;
  variable_definitions: VariableDefinition[];
  created_at: string;
  updated_at: string;
}

export interface AvailablePorts {
  suggested_game_port: number;
  suggested_rcon_port: number;
  used_ports: number[];
}

export interface TemplateCreateRequest {
  name: string;
  description?: string | null;
  yaml_template: string;
  variable_definitions: VariableDefinition[];
}

export interface TemplateUpdateRequest {
  name?: string;
  description?: string | null;
  yaml_template?: string;
  variable_definitions?: VariableDefinition[];
}

export interface DefaultVariablesResponse {
  variable_definitions: VariableDefinition[];
}
