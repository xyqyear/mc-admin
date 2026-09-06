package system

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func configurationRoundtrip(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	changes := []struct {
		name           string
		valid, invalid map[string]any
	}{
		{"dns", map[string]any{"dns_ttl": 45, "managed_sub_domain": "e2e", "dns": map[string]any{"type": "dnspod", "domain": "e2e.invalid", "id": "id", "key": "unused"}}, map[string]any{"dns": map[string]any{"type": "unknown"}}},
		{"snapshots", map[string]any{"ignored_paths": []any{".mcmap", "<LEVEL_NAME>/protected"}}, map[string]any{"ignored_paths": []any{"../escape"}}},
		{"players", map[string]any{"ignored_name_prefixes": []any{"bot_", "e2e_ignore_"}}, map[string]any{"heartbeat": map[string]any{"crash_threshold_minutes": 0}}},
		{"log_parser", map[string]any{"chat_pattern": `E2E: <(\S+)> (.*)`}, map[string]any{"uuid_patterns": 1}},
		{"mcmap", map[string]any{"batch_size": 8, "thread_count": 2}, map[string]any{"batch_size": 0}},
		{"world", map[string]any{"region_stat_workers": 4, "dimension_labels": map[string]any{".": "E2E 世界"}}, map[string]any{"dimension_max_depth_from_world_root": 33}},
		{"self_check", map[string]any{"retention_runs_keep_days": 7, "backup_mod_ids": []any{"FTBBackups2"}}, map[string]any{"snapshot_freshness_minutes": 0}},
	}
	stored := map[string]map[string]any{}
	for _, change := range changes {
		if err = t.Step("mutate and validate "+change.name+" without losing valid state", func() error {
			path := "/api/config/modules/" + change.name
			var module struct {
				Data map[string]any `json:"config_data"`
			}
			if err := client.JSON(ctx, "GET", path, nil, &module, 200); err != nil {
				return err
			}
			for key, value := range change.valid {
				module.Data[key] = value
			}
			var updated struct {
				Success bool           `json:"success"`
				Data    map[string]any `json:"updated_config"`
			}
			if err := client.JSON(ctx, "PUT", path, map[string]any{"config_data": module.Data}, &updated, 200); err != nil {
				return err
			}
			if !updated.Success {
				return fmt.Errorf("%s update did not report success", change.name)
			}
			for key, value := range change.valid {
				if change.name == "self_check" && key == "backup_mod_ids" {
					value = []any{"ftbbackups2"}
				}
				encoded, err := json.Marshal(value)
				if err != nil {
					return err
				}
				var expected any
				if err = json.Unmarshal(encoded, &expected); err != nil {
					return err
				}
				if !reflect.DeepEqual(updated.Data[key], expected) {
					return fmt.Errorf("%s ignored requested field %s", change.name, key)
				}
			}
			if err := client.JSON(ctx, "GET", path, nil, &module, 200); err != nil {
				return err
			}
			if !reflect.DeepEqual(module.Data, updated.Data) {
				return fmt.Errorf("%s read differs from acknowledged update", change.name)
			}
			stored[change.name] = module.Data
			if err := client.JSON(ctx, "PUT", path, map[string]any{"config_data": change.invalid}, nil, 400); err != nil {
				return err
			}
			if err := client.JSON(ctx, "GET", path, nil, &module, 200); err != nil {
				return err
			}
			if !reflect.DeepEqual(module.Data, stored[change.name]) {
				return fmt.Errorf("invalid %s update changed persistent configuration", change.name)
			}
			return nil
		}); err != nil {
			return err
		}
	}
	if err = t.Step("all modules survive process restart and reset to registered defaults", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		for name, expected := range stored {
			path := "/api/config/modules/" + name
			var module struct {
				Data map[string]any `json:"config_data"`
			}
			if err := client.JSON(ctx, "GET", path, nil, &module, 200); err != nil {
				return err
			}
			if !reflect.DeepEqual(module.Data, expected) {
				return fmt.Errorf("%s lost configuration on restart", name)
			}
			if err := client.JSON(ctx, "POST", path+"/reset", nil, nil, 200); err != nil {
				return err
			}
			if err := client.JSON(ctx, "GET", path, nil, &module, 200); err != nil {
				return err
			}
			if !reflect.DeepEqual(module.Data, fixtures.BackendOf(t.Env).Configs[name]) {
				return fmt.Errorf("%s reset differs from initial defaults", name)
			}
		}
		return nil
	}); err != nil {
		return err
	}
	for _, request := range []struct {
		method, suffix string
		code           int
	}{{"GET", "/schema", 404}, {"POST", "/reset", 404}, {"PUT", "", 400}} {
		if err = client.JSON(ctx, request.method, "/api/config/modules/unknown"+request.suffix, map[string]any{"config_data": map[string]any{}}, nil, request.code); err != nil {
			return err
		}
	}
	return nil
}

func metricsStaticValidation(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	if err = t.Step("system metrics are finite, bounded, and internally consistent", func() error {
		var info struct{ Used, Total float64 }
		var raw map[string]float64
		if err := client.JSON(ctx, "GET", "/api/system/info", nil, &raw, 200); err != nil {
			return err
		}
		info.Used, info.Total = raw["ramUsedGB"], raw["ramTotalGB"]
		if info.Total <= 0 || info.Used < 0 || info.Used > info.Total {
			return fmt.Errorf("invalid RAM metrics")
		}
		for _, key := range []string{"cpuLoad1Min", "cpuLoad5Min", "cpuLoad15Min"} {
			if v, ok := raw[key]; !ok || v < 0 {
				return fmt.Errorf("invalid %s", key)
			}
		}
		if err := client.JSON(ctx, "GET", "/api/system/disk-usage", nil, &raw, 200); err != nil {
			return err
		}
		if raw["diskTotalGB"] <= 0 || raw["diskUsedGB"] < 0 || raw["diskAvailableGB"] < 0 || raw["diskUsedGB"] > raw["diskTotalGB"] {
			return fmt.Errorf("invalid disk metrics")
		}
		if err := client.JSON(ctx, "GET", "/api/system/cpu_percent", nil, &raw, 200); err != nil {
			return err
		}
		if value, ok := raw["cpuPercentage"]; !ok || value < 0 || value > 100 {
			return fmt.Errorf("invalid CPU percentage")
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("production SPA, bundled assets, robots and API errors retain their wire contracts", func() error {
		var asset string
		for _, path := range []string{"/", "/servers/e2e-client-route"} {
			response, err := client.Do(ctx, "GET", path, nil, nil)
			if err != nil {
				return err
			}
			if err = client.Expect(response, 200); err != nil {
				return err
			}
			if !strings.Contains(response.Header.Get("Content-Type"), "text/html") || !strings.Contains(string(response.Body), `id="app-root"`) {
				return fmt.Errorf("%s did not serve application HTML", path)
			}
			matches := regexp.MustCompile(`(?:src|href)="(/assets/[^" ]+)"`).FindStringSubmatch(string(response.Body))
			if len(matches) != 2 {
				return fmt.Errorf("SPA omitted bundled asset reference")
			}
			asset = matches[1]
		}
		response, err := client.Do(ctx, "GET", asset, nil, nil)
		if err != nil {
			return err
		}
		if err = client.Expect(response, 200); err != nil {
			return err
		}
		if len(response.Body) == 0 {
			return fmt.Errorf("bundled asset empty")
		}
		response, err = client.Do(ctx, "GET", "/robots.txt", nil, nil)
		if err != nil {
			return err
		}
		if err = client.Expect(response, 200); err != nil {
			return err
		}
		if !strings.Contains(string(response.Body), "Disallow") {
			return fmt.Errorf("robots content missing crawler policy")
		}
		if err = client.JSON(ctx, "GET", "/api/nonexistent-route", nil, nil, 404); err != nil {
			return err
		}
		var invalid struct {
			Detail string `json:"detail"`
		}
		if err = client.JSON(ctx, "POST", "/api/admin/users", map[string]any{}, &invalid, 422); err != nil {
			return err
		}
		if !strings.Contains(invalid.Detail, "username") || !strings.Contains(invalid.Detail, "password") {
			return fmt.Errorf("validation error did not flatten missing fields")
		}
		return nil
	}); err != nil {
		return err
	}
	anonymous, err := fixtures.Session(ctx, t, "")
	if err != nil {
		return err
	}
	for _, path := range []string{"/api/system/info", "/api/system/disk-usage", "/api/system/cpu_percent"} {
		if err = anonymous.JSON(ctx, "GET", path, nil, nil, 401); err != nil {
			return err
		}
	}
	return anonymous.JSON(ctx, "GET", "/api/system/health", nil, nil, 200)
}

func auditRedaction(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	secret := fixtures.BackendOf(t.Env).Password + "-audit"
	t.Recorder.Redactor.Add(secret)
	body := map[string]any{
		"username": "audit-probe", "password": secret, "role": "admin",
		"nested": map[string]any{
			"access_token": secret,
			"task_id":      "audit-task-public", "status_code": 200,
			"items": []any{map[string]any{"private_key": secret}},
		},
	}
	if err = client.JSON(ctx, "POST", "/api/admin/users", body, nil, 200); err != nil {
		return err
	}
	if err = client.JSON(ctx, "POST", "/api/admin/users", body, nil, 400); err != nil {
		return err
	}
	if err = client.JSON(ctx, "GET", "/api/admin/users", nil, nil, 200); err != nil {
		return err
	}
	accessID := "e2e-audit-access-" + t.Env.ID
	t.Recorder.Redactor.Add(accessID)
	if err = t.Step("persist actual provider credential fields with DNS disabled", func() error {
		var module struct {
			Data map[string]any `json:"config_data"`
		}
		if err := client.JSON(ctx, "GET", "/api/config/modules/dns", nil, &module, 200); err != nil {
			return err
		}
		module.Data["enabled"] = false
		module.Data["dns"] = map[string]any{"type": "huawei", "domain": "audit.e2e.invalid", "ak": accessID, "sk": secret, "region": "cn-south-1"}
		if err := client.JSON(ctx, "PUT", "/api/config/modules/dns", map[string]any{"config_data": module.Data}, nil, 200); err != nil {
			return err
		}
		if err := client.JSON(ctx, "GET", "/api/config/modules/dns", nil, &module, 200); err != nil {
			return err
		}
		provider, ok := module.Data["dns"].(map[string]any)
		if !ok || module.Data["enabled"] != false || provider["ak"] != accessID || provider["sk"] != secret {
			return fmt.Errorf("provider credentials did not persist while DNS remained disabled")
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("audit masks login, user and provider fields; nested extras exercise middleware recursion", func() error {
		return api.Wait(ctx, 100*time.Millisecond, "audit entries flushed", func(context.Context) (bool, error) {
			data, err := os.ReadFile(filepath.Join(t.Env.Dir, "logs", "operations.log"))
			if err != nil {
				return false, err
			}
			if strings.Contains(string(data), secret) || strings.Contains(string(data), accessID) || strings.Contains(string(data), fixtures.BackendOf(t.Env).Password) {
				return false, api.Permanent(fmt.Errorf("audit output exposed a test credential"))
			}
			statuses := map[float64]bool{}
			providerAudited := false
			for _, line := range strings.Split(strings.TrimSpace(string(data)), "\n") {
				var entry map[string]any
				if err = json.Unmarshal([]byte(line), &entry); err != nil {
					return false, api.Permanent(err)
				}
				if entry["method"] == "GET" {
					return false, api.Permanent(fmt.Errorf("read-only request unexpectedly audited"))
				}
				request, ok := entry["request_body"].(map[string]any)
				if !ok {
					continue
				}
				if entry["path"] == "/api/config/modules/dns" && entry["method"] == "PUT" && entry["status_code"] == float64(200) {
					config, ok := request["config_data"].(map[string]any)
					if !ok {
						return false, api.Permanent(fmt.Errorf("audit omitted submitted DNS configuration"))
					}
					provider, ok := config["dns"].(map[string]any)
					if !ok || provider["ak"] != "***MASKED***" || provider["sk"] != "***MASKED***" || provider["type"] != "huawei" {
						return false, api.Permanent(fmt.Errorf("audit did not mask actual provider credential fields"))
					}
					providerAudited = true
				}
				if request["username"] != "audit-probe" {
					continue
				}
				if entry["username"] != "e2e-owner" || entry["role"] != "owner" || entry["timestamp"] == nil || entry["processing_time_ms"] == nil {
					return false, api.Permanent(fmt.Errorf("audit entry omitted actor/timing metadata"))
				}
				if request["password"] != "***MASKED***" {
					return false, api.Permanent(fmt.Errorf("audit password was not masked"))
				}
				nested, ok := request["nested"].(map[string]any)
				if !ok || nested["task_id"] != "audit-task-public" || nested["status_code"] != float64(200) {
					return false, api.Permanent(fmt.Errorf("audit overmasked public task or status fields"))
				}
				if nested["access_token"] != "***MASKED***" {
					return false, api.Permanent(fmt.Errorf("audit nested credential field was not masked"))
				}
				status, ok := entry["status_code"].(float64)
				if !ok {
					return false, api.Permanent(fmt.Errorf("audit omitted response status"))
				}
				statuses[status] = true
			}
			return statuses[200] && statuses[400] && providerAudited, nil
		})
	})
}
