import type { VariableDefinition } from "@/hooks/api/templateApi";
import type { VariableFormData } from "./variableSchemas";

// Helper to convert API variables to form data format
export const convertToFormData = (variables: VariableDefinition[]): VariableFormData[] => {
  return variables.map((v) => ({
    type: v.type,
    name: v.name,
    display_name: v.display_name,
    description: v.description,
    default: v.default,
    ...("min_value" in v ? { min_value: v.min_value } : {}),
    ...("max_value" in v ? { max_value: v.max_value } : {}),
    ...("max_length" in v ? { max_length: v.max_length } : {}),
    ...("pattern" in v ? { pattern: v.pattern } : {}),
    ...("options" in v ? { options: v.options } : {}),
  })) as VariableFormData[];
};

// Helper to convert form data to API format
export const convertToApiFormat = (variables: VariableFormData[]): VariableDefinition[] => {
  const includeDefault = (value: unknown) =>
    value !== undefined && value !== null ? { default: value } : {};

  return variables
    .filter((v) => v.name && v.display_name)
    .map((v) => {
      const base = {
        name: v.name,
        display_name: v.display_name,
        description: v.description,
      };

      switch (v.type) {
        case "int":
          return {
            ...base,
            type: "int" as const,
            ...includeDefault(v.default),
            min_value: v.min_value,
            max_value: v.max_value,
          };
        case "float":
          return {
            ...base,
            type: "float" as const,
            ...includeDefault(v.default),
            min_value: v.min_value,
            max_value: v.max_value,
          };
        case "string":
          return {
            ...base,
            type: "string" as const,
            ...includeDefault(v.default),
            max_length: v.max_length,
            pattern: v.pattern,
          };
        case "enum":
          return {
            ...base,
            type: "enum" as const,
            ...includeDefault(v.default),
            options: v.options || [],
          };
        case "bool":
          return {
            ...base,
            type: "bool" as const,
            ...includeDefault(v.default),
          };
      }
    }) as VariableDefinition[];
};
