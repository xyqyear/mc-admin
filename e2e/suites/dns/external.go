package dns

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/fixtures"
)

type record struct {
	Name  string `json:"sub_domain"`
	Type  string `json:"record_type"`
	Value string `json:"value"`
	TTL   int    `json:"ttl"`
	ID    any    `json:"record_id"`
}

type status struct {
	Initialized bool `json:"initialized"`
	DNSDiff     struct {
		Add    []record `json:"records_to_add"`
		Remove []string `json:"records_to_remove"`
		Update []record `json:"records_to_update"`
	} `json:"dns_diff"`
	RouterDiff struct {
		Add    map[string]string            `json:"routes_to_add"`
		Remove map[string]string            `json:"routes_to_remove"`
		Update map[string]map[string]string `json:"routes_to_update"`
	} `json:"router_diff"`
}

func (s status) clean() bool {
	return s.Initialized && len(s.DNSDiff.Add)+len(s.DNSDiff.Remove)+len(s.DNSDiff.Update)+len(s.RouterDiff.Add)+len(s.RouterDiff.Remove)+len(s.RouterDiff.Update) == 0
}

func external(provider string) func(context.Context, *engine.Scope) error {
	return func(ctx context.Context, t *engine.Scope) error {
		options := environment.Get[fixtures.Options](t.Env, "options")
		config, err := loadConfig(options.ExternalConfig, provider)
		if err != nil {
			return err
		}
		t.Recorder.Redactor.Add(config.ID, config.Key, config.AK, config.SK)
		scope := config.Prefix + "-" + t.Env.ID
		t.Recorder.Event("external_dns_scope", map[string]any{"provider": provider, "domain": config.Domain, "managed_sub_domain": scope, "router_image": routerImage})
		helperData, err := json.Marshal(map[string]any{"provider": provider, "scope": scope, "config": config})
		if err != nil {
			return err
		}
		if err = os.WriteFile(filepath.Join(t.Env.Dir, "dns-external.json"), helperData, 0600); err != nil {
			return err
		}
		if err = os.WriteFile(filepath.Join(t.Env.Dir, "dns-cleanup.py"), []byte(cleanupScript), 0600); err != nil {
			return err
		}
		if _, err = fixtures.DeploymentCommand(ctx, t.Env, "dns-scope-check", "python", "/data/dns-cleanup.py", "/data/dns-external.json", "check"); err != nil {
			return fmt.Errorf("external DNS read access and empty-scope preflight: %w", err)
		}
		t.Cleanup(func(cleanupCtx context.Context) error {
			output, err := fixtures.DeploymentCommand(cleanupCtx, t.Env, "dns-cloud-cleanup", "python", "/data/dns-cleanup.py", "/data/dns-external.json", "cleanup")
			t.Recorder.Event("external_dns_cleanup", map[string]any{"provider": provider, "domain": config.Domain, "managed_sub_domain": scope, "output": output})
			if err != nil {
				return fmt.Errorf("external DNS cleanup failed for %s.%s; remove only records under this generated scope: %w", scope, config.Domain, err)
			}
			return nil
		})
		if err = startRouter(ctx, t); err != nil {
			return err
		}
		client, err := fixtures.Session(ctx, t, "admin")
		if err != nil {
			return err
		}
		address := func(name, kind, value string, port int) map[string]any {
			return map[string]any{"type": "manual", "name": name, "record_type": kind, "value": value, "port": port}
		}
		primary := address("primary", "A", "192.0.2.10", 25565)
		secondary := address("secondary", "AAAA", "2001:db8::10", 25566)
		dynamic := map[string]any{"enabled": true, "dns": config.application(provider), "managed_sub_domain": scope, "mc_router_base_url": routerURL, "dns_ttl": config.TTL, "addresses": []any{primary, secondary}}
		if err = client.JSON(ctx, "PUT", "/api/config/modules/dns", map[string]any{"config_data": dynamic}, nil, 200); err != nil {
			return err
		}
		var enabled struct {
			Enabled bool `json:"enabled"`
		}
		if err = client.JSON(ctx, "GET", "/api/dns/enabled", nil, &enabled, 200); err != nil {
			return err
		}
		if !enabled.Enabled {
			return fmt.Errorf("configured provider remained disabled")
		}
		id := fixtures.ServerOf(t.Env).ID
		backend := fmt.Sprintf("localhost:%d", fixtures.ServerOf(t.Env).GamePort)
		route := func(name string) string { return id + "." + name + "." + scope + "." + config.Domain }
		expectedRecords := func(addresses ...map[string]any) map[string]string {
			expected := map[string]string{}
			for _, a := range addresses {
				base := a["name"].(string) + "." + scope
				expected["*."+base+"|"+a["record_type"].(string)] = a["value"].(string)
				expected["_minecraft._tcp."+id+"."+base+"|SRV"] = fmt.Sprintf("0 5 %v %s.%s.%s", a["port"], id, base, config.Domain)
			}
			return expected
		}
		if err = t.Step("preview enumerates exact A, AAAA, SRV and router additions without applying them", func() error {
			var current status
			if err := client.JSON(ctx, "GET", "/api/dns/status", nil, &current, 200); err != nil {
				return err
			}
			if !current.Initialized || len(current.DNSDiff.Add) != 4 || len(current.DNSDiff.Remove) != 0 || len(current.RouterDiff.Add) != 2 {
				return fmt.Errorf("unexpected initial external DNS diff")
			}
			var records []record
			if err := client.JSON(ctx, "GET", "/api/dns/records", nil, &records, 200); err != nil {
				return err
			}
			if len(records) != 0 {
				return fmt.Errorf("preview created DNS records")
			}
			var routes map[string]string
			if err := client.JSON(ctx, "GET", "/api/dns/routes", nil, &routes, 200); err != nil {
				return err
			}
			if len(routes) != 0 {
				return fmt.Errorf("preview created router mappings")
			}
			return nil
		}); err != nil {
			return err
		}
		if err = t.Step("reconciliation creates real provider records and router mappings and is idempotent", func() error {
			if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
				return err
			}
			if err := waitClean(ctx, client); err != nil {
				return err
			}
			if err := checkState(ctx, t, client, expectedRecords(primary, secondary), map[string]string{route("primary"): backend, route("secondary"): backend}, config.TTL); err != nil {
				return err
			}
			if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
				return err
			}
			return waitClean(ctx, client)
		}); err != nil {
			return err
		}
		if err = t.Step("configuration reinitialization and upstream route drift produce actionable updates", func() error {
			primary["value"] = "192.0.2.20"
			primary["port"] = 25567
			dynamic["mc_router_base_url"] = "http://localhost:26666"
			if err := client.JSON(ctx, "PUT", "/api/config/modules/dns", map[string]any{"config_data": dynamic}, nil, 200); err != nil {
				return err
			}
			if _, err := routerRequest(ctx, t, "POST", "/routes", map[string]string{"serverAddress": route("primary"), "backend": "localhost:1"}); err != nil {
				return err
			}
			var current status
			if err := client.JSON(ctx, "GET", "/api/dns/status", nil, &current, 200); err != nil {
				return err
			}
			if len(current.DNSDiff.Update) != 2 || current.RouterDiff.Update[route("primary")]["current"] != "localhost:1" || current.RouterDiff.Update[route("primary")]["target"] != backend {
				return fmt.Errorf("DNS or router drift was not detected")
			}
			if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
				return err
			}
			if err := waitClean(ctx, client); err != nil {
				return err
			}
			return checkState(ctx, t, client, expectedRecords(primary, secondary), map[string]string{route("primary"): backend, route("secondary"): backend}, config.TTL)
		}); err != nil {
			return err
		}
		return t.Step("record-type change and address removal reconcile CNAME and obsolete SRV/routes", func() error {
			primary["record_type"] = "CNAME"
			primary["value"] = "example.com"
			dynamic["addresses"] = []any{primary}
			if err := client.JSON(ctx, "PUT", "/api/config/modules/dns", map[string]any{"config_data": dynamic}, nil, 200); err != nil {
				return err
			}
			var current status
			if err := client.JSON(ctx, "GET", "/api/dns/status", nil, &current, 200); err != nil {
				return err
			}
			if len(current.DNSDiff.Remove) != 3 || len(current.DNSDiff.Add) != 1 || len(current.RouterDiff.Remove) != 1 {
				return fmt.Errorf("removal preview did not include obsolete address records and route")
			}
			if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
				return err
			}
			if err := waitClean(ctx, client); err != nil {
				return err
			}
			if err := checkState(ctx, t, client, expectedRecords(primary), map[string]string{route("primary"): backend}, config.TTL); err != nil {
				return err
			}
			var health struct {
				Findings []struct {
					Status string `json:"status"`
				} `json:"findings"`
			}
			if err := client.JSON(ctx, "POST", "/api/self-check/checks/dns.drift/run", nil, &health, 200); err != nil {
				return err
			}
			if len(health.Findings) != 1 || health.Findings[0].Status != "passed" {
				return fmt.Errorf("self-check still reports DNS drift after successful reconciliation")
			}
			retainedRecords := expectedRecords(primary)
			dynamic["enabled"] = false
			primary["value"] = "disabled.example.com"
			if err := client.JSON(ctx, "PUT", "/api/config/modules/dns", map[string]any{"config_data": dynamic}, nil, 200); err != nil {
				return err
			}
			if err := client.JSON(ctx, "GET", "/api/dns/enabled", nil, &enabled, 200); err != nil {
				return err
			}
			if enabled.Enabled {
				return fmt.Errorf("provider remained enabled after configuration disable")
			}
			if err := client.JSON(ctx, "GET", "/api/dns/routes", nil, nil, 503); err != nil {
				return err
			}
			owner, err := fixtures.Session(ctx, t, "owner")
			if err != nil {
				return err
			}
			if err := owner.JSON(ctx, "POST", "/api/servers/sync", map[string]any{"dry_run": false}, nil, 200); err != nil {
				return err
			}
			return checkProviderRecords(ctx, t, retainedRecords, config.TTL)
		})
	}
}

func waitClean(ctx context.Context, c *api.Client) error {
	return api.Wait(ctx, time.Second, "external provider and router convergence", func(ctx context.Context) (bool, error) {
		var current status
		if err := c.JSON(ctx, "GET", "/api/dns/status", nil, &current, 200); err != nil {
			return false, api.Permanent(err)
		}
		return current.clean(), nil
	})
}

func checkState(ctx context.Context, t *engine.Scope, c *api.Client, expectedRecords, expectedRoutes map[string]string, ttl int) error {
	var records []record
	if err := c.JSON(ctx, "GET", "/api/dns/records", nil, &records, 200); err != nil {
		return err
	}
	actual := map[string]string{}
	for _, r := range records {
		if r.ID == nil || r.ID == "" || r.TTL != ttl {
			return fmt.Errorf("provider record omitted identity or requested TTL")
		}
		actual[r.Name+"|"+r.Type] = strings.TrimSuffix(r.Value, ".")
	}
	if !reflect.DeepEqual(actual, expectedRecords) {
		return fmt.Errorf("provider records differ from expected scoped records: actual=%v expected=%v", actual, expectedRecords)
	}
	var routes map[string]string
	if err := c.JSON(ctx, "GET", "/api/dns/routes", nil, &routes, 200); err != nil {
		return err
	}
	if !reflect.DeepEqual(routes, expectedRoutes) {
		return fmt.Errorf("router maps differ from desired backend addresses")
	}
	return checkProviderRecords(ctx, t, expectedRecords, ttl)
}

func checkProviderRecords(ctx context.Context, t *engine.Scope, expected map[string]string, ttl int) error {
	output, err := fixtures.DeploymentCommand(ctx, t.Env, "dns-provider-inspect", "python", "/data/dns-cleanup.py", "/data/dns-external.json", "inspect")
	if err != nil {
		return err
	}
	var response struct {
		Records []struct {
			Name, Type string
			ID         any
			Values     []string
			TTL        int
		}
	}
	if err := json.Unmarshal([]byte(output), &response); err != nil {
		return err
	}
	if len(response.Records) != len(expected) {
		return fmt.Errorf("provider returned %d scoped records, expected %d", len(response.Records), len(expected))
	}
	actual := map[string]string{}
	for _, record := range response.Records {
		key := record.Name + "|" + record.Type
		if _, exists := actual[key]; exists || len(record.Values) != 1 || record.TTL != ttl || record.ID == nil {
			return fmt.Errorf("provider returned duplicate, multi-valued or invalid record %s", key)
		}
		actual[key] = strings.TrimSuffix(record.Values[0], ".")
	}
	if !reflect.DeepEqual(actual, expected) {
		return fmt.Errorf("independent provider records differ: actual=%v expected=%v", actual, expected)
	}
	return nil
}
