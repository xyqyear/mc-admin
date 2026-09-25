package dns

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type observedStatus struct {
	State          string          `json:"state"`
	DNSKnown       bool            `json:"dns_known"`
	RouterKnown    bool            `json:"router_known"`
	Issues         []string        `json:"issues"`
	UnknownServers []string        `json:"unknown_servers"`
	Empty          bool            `json:"empty_desired"`
	DNSDiff        json.RawMessage `json:"dns_diff"`
	RouterDiff     json.RawMessage `json:"router_diff"`
}

func ownedReconciliation(ctx context.Context, t *engine.Scope) error {
	if err := startRouter(ctx, t); err != nil {
		return err
	}
	if err := startOwnedDNSEdge(ctx, t); err != nil {
		return err
	}
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	t.Recorder.Redactor.Add("synthetic-dns-edge-secret", "e2e-owned-id", "e2e-owned-key")
	address := func(name, value string) map[string]any {
		return map[string]any{"type": "manual", "name": name, "record_type": "A", "value": value, "port": 25565}
	}
	primary := address("primary", "192.0.2.10")
	secondary := address("secondary", "192.0.2.11")
	third := address("third", "192.0.2.12")
	configuration := map[string]any{"enabled": true, "dns": map[string]any{"type": "dnspod", "domain": "e2e.invalid", "id": "e2e-owned-id", "key": "e2e-owned-key"}, "managed_sub_domain": "mc", "mc_router_base_url": "http://127.0.0.1:26667", "dns_ttl": 60, "addresses": []any{primary}}
	configure := func() error {
		return client.JSON(ctx, "PUT", "/api/config/modules/dns", map[string]any{"config_data": configuration}, nil, 200)
	}
	observe := func(expected string, dnsKnown, routerKnown bool) error {
		var result observedStatus
		if err := client.JSON(ctx, "GET", "/api/dns/status", nil, &result, 200); err != nil {
			return err
		}
		if result.State != expected || result.DNSKnown != dnsKnown || result.RouterKnown != routerKnown {
			return fmt.Errorf("unexpected connectivity observation: %+v", result)
		}
		if !dnsKnown && string(result.DNSDiff) != "null" {
			return fmt.Errorf("unknown provider became empty diff")
		}
		if !routerKnown && string(result.RouterDiff) != "null" {
			return fmt.Errorf("unknown router became empty diff")
		}
		if expected == "degraded" && len(result.Issues) == 0 {
			return fmt.Errorf("degraded state has no actionable issue")
		}
		return nil
	}
	if err = configure(); err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	route := func(name string) string { return id + "." + name + ".mc.e2e.invalid" }
	backend := fmt.Sprintf("localhost:%d", fixtures.ServerOf(t.Env).GamePort)
	if err = t.Step("real SDK observes and applies through owned TLS edge; unchanged update emits zero writes", func() error {
		if err := observe("pending", true, true); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
			return err
		}
		if err := observe("ready", true, true); err != nil {
			return err
		}
		var records []record
		if err := client.JSON(ctx, "GET", "/api/dns/records", nil, &records, 200); err != nil {
			return err
		}
		if len(records) != 2 || records[0].TTL != 60 || records[1].TTL != 60 {
			return fmt.Errorf("public record inventory does not reflect the provider: %+v", records)
		}
		if _, err := edgeControl(ctx, t, map[string]any{"clear_calls": true}); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
			return err
		}
		state, err := edgeControl(ctx, t, nil)
		if err != nil {
			return err
		}
		if len(state.Calls) != 0 || len(state.Records) != 2 {
			return fmt.Errorf("unchanged state wrote records/routes: %+v", state)
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("unknown provider preserves records while healthy router converges and full health continues safely", func() error {
		if _, err := edgeControl(ctx, t, map[string]any{"dns_read_failure": true, "clear_calls": true}); err != nil {
			return err
		}
		configuration["addresses"] = []any{primary, secondary}
		if err := configure(); err != nil {
			return err
		}
		if err := observe("degraded", false, true); err != nil {
			return err
		}
		if err := safeFailedUpdate(ctx, client); err != nil {
			return err
		}
		state, err := edgeControl(ctx, t, nil)
		if err != nil {
			return err
		}
		if len(state.Records) != 2 {
			return fmt.Errorf("unknown provider records were changed")
		}
		for _, call := range state.Calls {
			if call["target"] == "dns" {
				return fmt.Errorf("unknown provider received mutation")
			}
		}
		var routes map[string]string
		if err := client.JSON(ctx, "GET", "/api/dns/routes", nil, &routes, 200); err != nil {
			return err
		}
		if routes[route("primary")] != backend || routes[route("secondary")] != backend {
			return fmt.Errorf("healthy router did not converge: %+v", routes)
		}
		if err := client.JSON(ctx, "POST", "/api/servers/sync", map[string]any{"dry_run": false}, nil, 200); err != nil {
			return err
		}
		if err := checkDegradedHealth(ctx, client); err != nil {
			return err
		}
		return fixtures.Status(ctx, client, id, "exists")
	}); err != nil {
		return err
	}
	if _, err = edgeControl(ctx, t, map[string]any{"dns_read_failure": false}); err != nil {
		return err
	}
	if err = client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
		return err
	}
	if err = observe("ready", true, true); err != nil {
		return err
	}
	if err = t.Step("unknown router preserves routes while provider applies and fresh retry restores ready", func() error {
		if _, err := edgeControl(ctx, t, map[string]any{"router_read_failure": true, "clear_calls": true}); err != nil {
			return err
		}
		primary["value"] = "192.0.2.20"
		if err := configure(); err != nil {
			return err
		}
		if err := observe("degraded", true, false); err != nil {
			return err
		}
		if err := safeFailedUpdate(ctx, client); err != nil {
			return err
		}
		state, err := edgeControl(ctx, t, nil)
		if err != nil {
			return err
		}
		changed := false
		for _, r := range state.Records {
			changed = changed || (r["Name"] == "*.primary.mc" && r["Value"] == "192.0.2.20")
		}
		if !changed {
			return fmt.Errorf("healthy provider did not apply changed address")
		}
		for _, call := range state.Calls {
			if call["target"] == "router" {
				return fmt.Errorf("unknown router received mutation")
			}
		}
		if _, err := edgeControl(ctx, t, map[string]any{"router_read_failure": false}); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
			return err
		}
		return observe("ready", true, true)
	}); err != nil {
		return err
	}
	if err = t.Step("single target failure leaves unrelated additions and unchanged route intact; retry fills only missing record", func() error {
		if _, err := edgeControl(ctx, t, map[string]any{"fail_name": "*.third.mc", "clear_calls": true}); err != nil {
			return err
		}
		configuration["addresses"] = []any{primary, secondary, third}
		if err := configure(); err != nil {
			return err
		}
		if err := safeFailedUpdate(ctx, client); err != nil {
			return err
		}
		if err := observe("degraded", true, true); err != nil {
			return err
		}
		state, err := edgeControl(ctx, t, nil)
		if err != nil {
			return err
		}
		if len(state.Records) != 5 {
			return fmt.Errorf("single failed target prevented unrelated write: %+v", state.Records)
		}
		for _, call := range state.Calls {
			if call["target"] == "router" && call["action"] == "DELETE" {
				return fmt.Errorf("route add deleted existing routing table")
			}
		}
		if _, err := edgeControl(ctx, t, map[string]any{"fail_name": nil, "clear_calls": true}); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
			return err
		}
		state, err = edgeControl(ctx, t, nil)
		if err != nil {
			return err
		}
		if len(state.Calls) != 1 || len(state.Records) != 6 {
			return fmt.Errorf("retry repeated settled targets: %+v", state)
		}
		if _, err := routerRequest(ctx, t, "POST", "/routes", map[string]string{"serverAddress": route("secondary"), "backend": "localhost:1"}); err != nil {
			return err
		}
		if _, err := edgeControl(ctx, t, map[string]any{"clear_calls": true}); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
			return err
		}
		state, err = edgeControl(ctx, t, nil)
		if err != nil {
			return err
		}
		if len(state.Calls) != 1 || state.Calls[0]["target"] != "router" || state.Calls[0]["action"] != "POST" {
			return fmt.Errorf("changed backend was not a single upsert: %+v", state.Calls)
		}
		return observe("ready", true, true)
	}); err != nil {
		return err
	}
	if err = t.Step("empty desired state and manual disable retain actual DNS records and routes", func() error {
		configuration["addresses"] = []any{}
		if err := configure(); err != nil {
			return err
		}
		if err := observe("empty", true, true); err != nil {
			return err
		}
		if _, err := edgeControl(ctx, t, map[string]any{"clear_calls": true}); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 200); err != nil {
			return err
		}
		state, err := edgeControl(ctx, t, nil)
		if err != nil {
			return err
		}
		if len(state.Calls) != 0 || len(state.Records) != 6 {
			return fmt.Errorf("empty target deleted connectivity")
		}
		configuration["enabled"] = false
		if err := configure(); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", "/api/dns/update", nil, nil, 503); err != nil {
			return err
		}
		return nil
	}); err != nil {
		return err
	}
	logs, err := fixtures.BackendOf(t.Env).Docker.Run(ctx, "logs", fixtures.BackendOf(t.Env).Name)
	if err != nil {
		return err
	}
	if strings.Contains(logs, "synthetic-dns-edge-secret") {
		return fmt.Errorf("provider error leaked through application logs")
	}
	appLog, err := fixtures.BackendOf(t.Env).Docker.Run(ctx, "exec", fixtures.BackendOf(t.Env).Name, "python", "-c", "from pathlib import Path; print('exposed' if 'synthetic-dns-edge-secret' in Path('/data/logs/app.log').read_text() else 'clear')")
	if err != nil {
		return err
	}
	if strings.TrimSpace(appLog) != "clear" {
		return fmt.Errorf("provider error leaked through persisted application log")
	}
	return nil
}

func safeFailedUpdate(ctx context.Context, client *api.Client) error {
	var response map[string]any
	if err := client.JSON(ctx, "POST", "/api/dns/update", nil, &response, 500); err != nil {
		return err
	}
	data, err := json.Marshal(response)
	if err != nil {
		return err
	}
	if strings.Contains(string(data), "synthetic-dns-edge-secret") {
		return fmt.Errorf("provider error leaked through failed update response")
	}
	return nil
}

func checkDegradedHealth(ctx context.Context, client *api.Client) error {
	var health struct {
		ID       string  `json:"id"`
		Error    *string `json:"error_message"`
		Findings []struct {
			Check    string         `json:"check_id"`
			Status   string         `json:"status"`
			Evidence map[string]any `json:"evidence"`
		} `json:"findings"`
	}
	if err := client.JSON(ctx, "POST", "/api/self-check/run", nil, &health, 200); err != nil {
		return err
	}
	if health.ID == "" || health.Error != nil {
		return fmt.Errorf("one degraded dependency failed the entire health run")
	}
	dns, continued := false, false
	for _, finding := range health.Findings {
		dns = dns || (finding.Check == "dns.drift" && finding.Status == "warning" && finding.Evidence["dns_known"] == false)
		continued = continued || (finding.Check == "dependency.binaries" && finding.Status == "passed")
	}
	if !dns || !continued {
		return fmt.Errorf("health omitted degraded evidence or unrelated checks: %+v", health)
	}
	data, err := json.Marshal(health)
	if err != nil {
		return err
	}
	if strings.Contains(string(data), "synthetic-dns-edge-secret") {
		return fmt.Errorf("provider error leaked in health result")
	}
	return client.JSON(ctx, "GET", "/api/self-check/runs/"+health.ID, nil, nil, 200)
}
