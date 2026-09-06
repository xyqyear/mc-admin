package fixtures

import "mc-admin/e2e/internal/environment"

func TemplateDefinition(env *environment.Environment) map[string]any {
	return map[string]any{
		"name": "E2E template", "description": "Public API fixture",
		"yaml_template": Compose(env, "{name}", "{game_port}", "{rcon_port}"),
		"variable_definitions": []map[string]any{
			{"type": "string", "name": "name", "display_name": "Name", "max_length": 20, "pattern": "^[a-z0-9-]+$"},
			{"type": "int", "name": "game_port", "display_name": "Game port", "min_value": 1024, "max_value": 65535},
			{"type": "int", "name": "rcon_port", "display_name": "RCON port", "min_value": 1024, "max_value": 65535},
		},
	}
}
