package templates

import (
	"context"
	"fmt"
	"reflect"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func variables(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	definition := fixtures.TemplateDefinition(t.Env)
	defs := definition["variable_definitions"].([]map[string]any)
	defs = append(defs,
		map[string]any{"type": "float", "name": "ratio", "display_name": "Ratio", "min_value": 0.5, "max_value": 2.5, "default": 1.5},
		map[string]any{"type": "enum", "name": "mode", "display_name": "Mode", "options": []string{"easy", "hard"}, "default": "easy"},
		map[string]any{"type": "bool", "name": "enabled", "display_name": "Enabled", "default": false})
	definition["variable_definitions"] = defs
	definition["yaml_template"] = definition["yaml_template"].(string) + "x-e2e: '{ratio} {mode} {enabled}'\n"
	var created struct {
		ID int `json:"id"`
	}
	if err = c.JSON(ctx, "POST", "/api/templates/", definition, &created, 201); err != nil {
		return err
	}
	base := fmt.Sprintf("/api/templates/%d", created.ID)
	var listed []struct {
		ID    int `json:"id"`
		Count int `json:"variable_count"`
	}
	if err = c.JSON(ctx, "GET", "/api/templates/", nil, &listed, 200); err != nil {
		return err
	}
	if len(listed) != 1 || listed[0].ID != created.ID || listed[0].Count != len(defs) {
		return fmt.Errorf("template listing differs from stored definition")
	}
	if err = t.Step("schema and preview preserve all five variable types", func() error {
		var schema struct {
			Schema struct {
				Properties map[string]map[string]any `json:"properties"`
			} `json:"json_schema"`
		}
		if err := c.JSON(ctx, "GET", base+"/schema", nil, &schema, 200); err != nil {
			return err
		}
		for name, kind := range map[string]string{"name": "string", "game_port": "integer", "ratio": "number", "mode": "string", "enabled": "boolean"} {
			if schema.Schema.Properties[name]["type"] != kind {
				return fmt.Errorf("schema type for %s is not %s", name, kind)
			}
		}
		values := map[string]any{"name": "typed", "game_port": 22001, "rcon_port": 22002, "ratio": 1.25, "mode": "hard", "enabled": true}
		var preview struct {
			YAML string `json:"rendered_yaml"`
		}
		if err := c.JSON(ctx, "POST", base+"/preview", map[string]any{"variable_values": values}, &preview, 200); err != nil {
			return err
		}
		if !strings.Contains(preview.YAML, "1.25 hard True") {
			return fmt.Errorf("typed preview missing substituted values")
		}
		for _, bad := range []struct {
			key   string
			value any
		}{{"name", "UPPER"}, {"name", strings.Repeat("a", 21)}, {"game_port", true}, {"game_port", 70000}, {"ratio", 0.1}, {"ratio", false}, {"mode", "invalid"}, {"enabled", "true"}} {
			original := values[bad.key]
			values[bad.key] = bad.value
			if err := c.JSON(ctx, "POST", base+"/preview", map[string]any{"variable_values": values}, nil, 400); err != nil {
				return err
			}
			values[bad.key] = original
		}
		delete(values, "enabled")
		return c.JSON(ctx, "POST", base+"/preview", map[string]any{"variable_values": values}, nil, 400)
	}); err != nil {
		return err
	}
	if err = t.Step("invalid and duplicate definitions are rejected without altering the template", func() error {
		if err := c.JSON(ctx, "POST", "/api/templates/", definition, nil, 409); err != nil {
			return err
		}
		if err := c.JSON(ctx, "PUT", base, map[string]any{"variable_definitions": append(defs, defs[0])}, nil, 400); err != nil {
			return err
		}
		if err := c.JSON(ctx, "PUT", base, map[string]any{"yaml_template": definition["yaml_template"].(string) + "x-missing: '{undefined}'\n"}, nil, 400); err != nil {
			return err
		}
		if err := c.JSON(ctx, "PUT", base, map[string]any{"name": ""}, nil, 422); err != nil {
			return err
		}
		var savedTemplate, afterRejected map[string]any
		if err := c.JSON(ctx, "GET", base, nil, &savedTemplate, 200); err != nil {
			return err
		}
		for _, invalid := range []map[string]any{
			{"type": "string", "name": "name", "display_name": "Name", "pattern": "["},
			{"type": "string", "name": "name", "display_name": "Name", "max_length": 2, "default": "long"},
			{"type": "int", "name": "game_port", "display_name": "Port", "min_value": 65535, "max_value": 1024},
		} {
			badDefs := append([]map[string]any(nil), defs...)
			for i, existing := range badDefs {
				if existing["name"] == invalid["name"] {
					badDefs[i] = invalid
				}
			}
			if err := c.JSON(ctx, "PUT", base, map[string]any{"variable_definitions": badDefs}, nil, 400); err != nil {
				return err
			}
			if err := c.JSON(ctx, "PUT", "/api/templates/default-variables", map[string]any{"variable_definitions": badDefs}, nil, 400); err != nil {
				return err
			}
		}
		if err := c.JSON(ctx, "GET", base, nil, &afterRejected, 200); err != nil {
			return err
		}
		if !reflect.DeepEqual(savedTemplate, afterRejected) {
			return fmt.Errorf("invalid definition update modified the saved template")
		}
		for _, route := range []string{"/api/templates/999999", "/api/templates/999999/schema"} {
			if err := c.JSON(ctx, "GET", route, nil, nil, 404); err != nil {
				return err
			}
		}
		return c.JSON(ctx, "DELETE", "/api/templates/999999", nil, nil, 404)
	}); err != nil {
		return err
	}
	if err = t.Step("default definitions persist across a backend restart and reject duplicate names", func() error {
		var before, after map[string]any
		if err := c.JSON(ctx, "PUT", "/api/templates/default-variables", map[string]any{"variable_definitions": defs}, &before, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "PUT", "/api/templates/default-variables", map[string]any{"variable_definitions": append(defs, defs[0])}, nil, 400); err != nil {
			return err
		}
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		if err := c.JSON(ctx, "GET", "/api/templates/default-variables", nil, &after, 200); err != nil {
			return err
		}
		if !reflect.DeepEqual(before, after) {
			return fmt.Errorf("default variables did not survive restart unchanged")
		}
		return nil
	}); err != nil {
		return err
	}
	var ports struct {
		Game int   `json:"suggested_game_port"`
		RCON int   `json:"suggested_rcon_port"`
		Used []int `json:"used_ports"`
	}
	if err = c.JSON(ctx, "GET", "/api/templates/ports/available", nil, &ports, 200); err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	seen := map[int]bool{}
	for _, port := range ports.Used {
		seen[port] = true
	}
	if !seen[server.GamePort] || !seen[server.RCONPort] || seen[ports.Game] || seen[ports.RCON] || ports.Game == ports.RCON {
		return fmt.Errorf("available-port suggestions overlap known server ports: %+v", ports)
	}
	return nil
}
