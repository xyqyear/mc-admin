package system

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "system.discovery", Suite: "system", Tags: []string{"smoke"}, Recipe: recipes.Base, Isolation: engine.ObserveReuse, Timeout: time.Minute, Run: discovery},
		{ID: "system.configuration-catalog", Suite: "system", Tags: []string{"smoke"}, Recipe: recipes.Base, Isolation: engine.ObserveReuse, Timeout: time.Minute, Run: configurationCatalog},
		{ID: "system.configuration-persistence", Suite: "system", Tags: []string{"smoke"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: persistence},
		{ID: "system.events-handshake", Suite: "system", Tags: []string{"smoke"}, Recipe: recipes.Base, Isolation: engine.ObserveReuse, Timeout: time.Minute, Run: events},
		{ID: "system.configuration-roundtrip", Suite: "system", Tags: []string{"regression"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: configurationRoundtrip},
		{ID: "system.metrics-static-validation", Suite: "system", Tags: []string{"regression"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: time.Minute, Run: metricsStaticValidation},
		{ID: "system.audit-redaction", Suite: "system", Tags: []string{"regression"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: time.Minute, Run: auditRedaction},
	}
}

func events(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	return t.Step("authenticated WebSocket reports invalid cursor reset", func() error {
		return client.WebSocket(ctx, "/api/events?since=invalid", func(event map[string]any) (bool, error) {
			if event["type"] == "heartbeat" {
				return false, nil
			}
			if event["type"] != "stream_reset" || event["reason"] != "invalid_cursor" {
				return false, fmt.Errorf("unexpected event reset: %v", event)
			}
			return true, nil
		})
	})
}

func discovery(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	return t.Step("startup exposes persistent registries and empty business inventories", func() error {
		for _, path := range []string{"/api/system/health", "/api/system/info", "/api/system/disk-usage", "/api/self-check/catalog", "/api/self-check/status", "/api/cron/registered", "/api/cron/", "/api/players/", "/api/dns/enabled"} {
			if err := client.JSON(ctx, "GET", path, nil, nil, 200); err != nil {
				return err
			}
		}
		for _, path := range []string{"/api/servers/", "/api/servers/overview", "/api/templates/"} {
			var items []json.RawMessage
			if err := client.JSON(ctx, "GET", path, nil, &items, 200); err != nil {
				return err
			}
			if len(items) != 0 {
				return fmt.Errorf("expected empty %s, got %d items", path, len(items))
			}
		}
		return nil
	})
}

func configurationCatalog(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	return t.Step("all dynamic modules expose readable configuration and schemas", func() error {
		var response struct {
			Modules map[string]any `json:"modules"`
		}
		if err := client.JSON(ctx, "GET", "/api/config/modules", nil, &response, 200); err != nil {
			return err
		}
		for _, name := range []string{"dns", "snapshots", "players", "log_parser", "mcmap", "world", "self_check"} {
			if _, ok := response.Modules[name]; !ok {
				return fmt.Errorf("missing config module %s", name)
			}
			for _, suffix := range []string{"", "/schema"} {
				if err := client.JSON(ctx, "GET", "/api/config/modules/"+name+suffix, nil, nil, 200); err != nil {
					return err
				}
			}
		}
		return client.JSON(ctx, "GET", "/api/config/modules/does-not-exist", nil, nil, 404)
	})
}

func persistence(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	var module struct {
		Data map[string]any `json:"config_data"`
	}
	path := "/api/config/modules/world"
	if err = client.JSON(ctx, "GET", path, nil, &module, 200); err != nil {
		return err
	}
	module.Data["dimension_labels"] = map[string]any{".": "E2E persisted label"}
	if err = t.Step("configuration changes are readable immediately", func() error {
		if err := client.JSON(ctx, "PUT", path, map[string]any{"config_data": module.Data}, nil, 200); err != nil {
			return err
		}
		return checkLabel(ctx, t, path)
	}); err != nil {
		return err
	}
	return t.Step("real backend restart preserves data and browser sessions", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		if err := client.JSON(ctx, "GET", "/api/user/me", nil, nil, 200); err != nil {
			return err
		}
		return checkLabel(ctx, t, path)
	})
}

func checkLabel(ctx context.Context, t *engine.Scope, path string) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	var module struct {
		Data struct {
			Labels map[string]string `json:"dimension_labels"`
		} `json:"config_data"`
	}
	if err := client.JSON(ctx, "GET", path, nil, &module, 200); err != nil {
		return err
	}
	if module.Data.Labels["."] != "E2E persisted label" {
		return fmt.Errorf("configuration did not persist: %v", module.Data.Labels)
	}
	return nil
}
