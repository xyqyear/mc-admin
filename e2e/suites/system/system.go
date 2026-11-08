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
		{ID: "system.configuration-credential-logs", Suite: "system", Tags: []string{"regression", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: configurationCredentialLogs},
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
		for _, path := range []string{"/api/system/health", "/api/monitoring", "/api/self-check/catalog", "/api/self-check/status", "/api/cron/registered", "/api/cron/", "/api/players/", "/api/dns/enabled"} {
			if err := client.JSON(ctx, "GET", path, nil, nil, 200); err != nil {
				return err
			}
		}
		for _, path := range []string{"/api/servers/", "/api/templates/"} {
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
	return t.Step("settings resources expose their concrete configuration", func() error {
		for name, field := range map[string]string{"dns": "dns", "snapshots": "time_restriction", "players": "heartbeat", "log-parser": "chat_pattern", "mcmap": "batch_size", "world": "dimension_labels", "self-check": "checks"} {
			var settings map[string]any
			if err := client.JSON(ctx, "GET", "/api/settings/"+name, nil, &settings, 200); err != nil {
				return err
			}
			if _, ok := settings[field]; !ok {
				return fmt.Errorf("settings %s omitted %s", name, field)
			}
		}
		return client.JSON(ctx, "GET", "/api/settings/does-not-exist", nil, nil, 404)
	})
}

func persistence(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	var module map[string]any
	path := "/api/settings/world"
	if err = client.JSON(ctx, "GET", path, nil, &module, 200); err != nil {
		return err
	}
	module["dimension_labels"] = map[string]any{".": "E2E persisted label"}
	if err = t.Step("configuration changes are readable immediately", func() error {
		if err := client.JSON(ctx, "PUT", path, module, nil, 200); err != nil {
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
		Labels map[string]string `json:"dimension_labels"`
	}
	if err := client.JSON(ctx, "GET", path, nil, &module, 200); err != nil {
		return err
	}
	if module.Labels["."] != "E2E persisted label" {
		return fmt.Errorf("configuration did not persist: %v", module.Labels)
	}
	return nil
}
