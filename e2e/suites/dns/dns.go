package dns

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(r fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "dns.disabled-and-validation", Suite: "dns", Tags: []string{"regression"}, Recipe: r.Base, Isolation: engine.Fresh, Timeout: time.Minute, Run: disabled},
		{ID: "dns.dnspod-reconciliation", Suite: "dns", Tags: []string{"external", "dns"}, Recipe: r.Server, Isolation: engine.Fresh, Timeout: 8 * time.Minute, Run: external("dnspod")},
		{ID: "dns.huawei-reconciliation", Suite: "dns", Tags: []string{"external", "dns"}, Recipe: r.Server, Isolation: engine.Fresh, Timeout: 8 * time.Minute, Run: external("huawei")},
	}
}

func disabled(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	return t.Step("disabled DNS exposes state and rejects operations without touching external providers", func() error {
		var enabled struct {
			Enabled bool `json:"enabled"`
		}
		if err := c.JSON(ctx, "GET", "/api/dns/enabled", nil, &enabled, 200); err != nil {
			return err
		}
		if enabled.Enabled {
			return fmt.Errorf("fresh deployment unexpectedly enables cloud DNS")
		}
		for _, path := range []string{"/status", "/records", "/routes"} {
			if err := c.JSON(ctx, "GET", "/api/dns"+path, nil, nil, 503); err != nil {
				return err
			}
		}
		if err := c.JSON(ctx, "POST", "/api/dns/update", nil, nil, 503); err != nil {
			return err
		}
		for _, invalid := range []map[string]any{
			{"dns": map[string]any{"type": "invalid-provider"}},
			{"addresses": []any{map[string]any{"name": "same"}, map[string]any{"name": "same"}}},
			{"addresses": []any{map[string]any{"record_type": "TXT"}}},
		} {
			if err := c.JSON(ctx, "PUT", "/api/config/modules/dns", map[string]any{"config_data": invalid}, nil, 400); err != nil {
				return err
			}
		}
		if err := c.JSON(ctx, "GET", "/api/dns/enabled", nil, &enabled, 200); err != nil {
			return err
		}
		if enabled.Enabled {
			return fmt.Errorf("invalid configuration enabled DNS")
		}
		anonymous, err := fixtures.Session(ctx, t, "")
		if err != nil {
			return err
		}
		for _, path := range []string{"/enabled", "/status", "/records", "/routes"} {
			if err := anonymous.JSON(ctx, "GET", "/api/dns"+path, nil, nil, 401); err != nil {
				return err
			}
		}
		return anonymous.JSON(ctx, "POST", "/api/dns/update", nil, nil, 401)
	})
}
