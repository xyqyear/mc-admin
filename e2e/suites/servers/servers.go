package servers

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "servers.template-snapshot", Suite: "servers", Tags: []string{"smoke"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: templateSnapshot},
		{ID: "servers.compose-conversions-and-rebuild", Suite: "servers", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: conversions},
		{ID: "servers.restart-schedule-and-creation", Suite: "servers", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: schedules},
		{ID: "servers.sync-reconciliation", Suite: "servers", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: reconciliation},
	}
}

func templateSnapshot(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	if err = t.Step("direct server exists and rejects duplicate creation", func() error {
		if err := fixtures.Status(ctx, client, server.ID, "exists"); err != nil {
			return err
		}
		return client.JSON(ctx, "POST", "/api/servers/"+server.ID, map[string]any{"yaml_content": server.Compose}, nil, 409)
	}); err != nil {
		return err
	}
	if err = fixtures.Operation(ctx, client, server.ID, "remove"); err != nil {
		return err
	}
	var template struct {
		ID int `json:"id"`
	}
	if err = client.JSON(ctx, "POST", "/api/templates/", fixtures.TemplateDefinition(t.Env), &template, 201); err != nil {
		return err
	}
	if err = t.Step("create server from a template and retain its snapshot after deletion", func() error {
		if err := client.JSON(ctx, "POST", "/api/servers/"+server.ID, map[string]any{"template_id": template.ID, "variable_values": map[string]any{"name": server.ID, "game_port": server.GamePort, "rcon_port": server.RCONPort}}, nil, 200); err != nil {
			return err
		}
		if err := client.JSON(ctx, "DELETE", fmt.Sprintf("/api/templates/%d", template.ID), nil, nil, 204); err != nil {
			return err
		}
		var info struct {
			Port int    `json:"gamePort"`
			ID   string `json:"id"`
		}
		if err := client.JSON(ctx, "GET", "/api/servers/"+server.ID, nil, &info, 200); err != nil {
			return err
		}
		if info.Port != server.GamePort || info.ID != server.ID {
			return fmt.Errorf("incorrect server metadata: %+v", info)
		}
		return client.JSON(ctx, "GET", "/api/servers/"+server.ID+"/template-config", nil, nil, 200)
	}); err != nil {
		return err
	}
	return t.Step("remove through the lifecycle API", func() error {
		if err := fixtures.Operation(ctx, client, server.ID, "remove"); err != nil {
			return err
		}
		return client.JSON(ctx, "GET", "/api/servers/"+server.ID, nil, nil, 404)
	})
}
