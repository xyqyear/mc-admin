package templates

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "templates.lifecycle", Suite: "templates", Tags: []string{"smoke"}, Recipe: recipes.Base, Isolation: engine.CleanReuse, Timeout: time.Minute, Run: lifecycle},
		{ID: "templates.types-defaults-and-boundaries", Suite: "templates", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: variables},
	}
}

func lifecycle(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	var template struct {
		ID   int    `json:"id"`
		Name string `json:"name"`
	}
	if err = t.Step("create a reusable template with typed variables", func() error {
		return client.JSON(ctx, "POST", "/api/templates/", fixtures.TemplateDefinition(t.Env), &template, 201)
	}); err != nil {
		return err
	}
	path := fmt.Sprintf("/api/templates/%d", template.ID)
	deleted := false
	t.Cleanup(func(ctx context.Context) error {
		if deleted {
			return nil
		}
		return client.JSON(ctx, "DELETE", path, nil, nil, 204)
	})
	if err = t.Step("render valid values and reject an out-of-range port", func() error {
		if err := client.JSON(ctx, "GET", path+"/schema", nil, nil, 200); err != nil {
			return err
		}
		var preview struct {
			YAML string `json:"rendered_yaml"`
		}
		values := map[string]any{"name": "preview", "game_port": 23456, "rcon_port": 23457}
		if err := client.JSON(ctx, "POST", path+"/preview", map[string]any{"variable_values": values}, &preview, 200); err != nil {
			return err
		}
		if !strings.Contains(preview.YAML, "mc-preview") || strings.Contains(preview.YAML, "{game_port}") {
			return fmt.Errorf("template was not rendered correctly")
		}
		values["game_port"] = 70000
		return client.JSON(ctx, "POST", path+"/preview", map[string]any{"variable_values": values}, nil, 400)
	}); err != nil {
		return err
	}
	if err = t.Step("update then read the persisted template", func() error {
		if err := client.JSON(ctx, "PUT", path, map[string]string{"name": "Edited E2E template"}, nil, 200); err != nil {
			return err
		}
		if err := client.JSON(ctx, "GET", path, nil, &template, 200); err != nil {
			return err
		}
		if template.Name != "Edited E2E template" {
			return fmt.Errorf("template update was not persisted")
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("delete the template and verify absence", func() error {
		if err := client.JSON(ctx, "DELETE", path, nil, nil, 204); err != nil {
			return err
		}
		deleted = true
		return client.JSON(ctx, "GET", path, nil, nil, 404)
	})
}
