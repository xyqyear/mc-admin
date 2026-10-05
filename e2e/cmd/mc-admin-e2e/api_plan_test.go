package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"strings"
	"testing"

	"mc-admin/e2e/internal/engine"
)

func TestAPIHistoryRejectsInvalidPayloadWithoutHidingCurrentCases(t *testing.T) {
	path := filepath.Join(t.TempDir(), "history.json")
	fallback, _, err := restoredCosts("", "regression", "context")
	if err != nil {
		t.Fatal(err)
	}
	valid := map[string]any{"schema_version": 1, "component": "api", "profile": "regression", "compatibility": "context", "audited": true, "source": map[string]any{"run_id": "123", "sha": strings.Repeat("a", 40)}, "costs": map[string]any{"version": 1, "measurement": "api-lifecycle-v2", "default_seconds": 23, "cases": map[string]any{"unknown.case": 12}, "recipes": map[string]any{}, "shard_overhead_seconds": 2}}
	for _, mutation := range []string{"valid", "negative", "unaudited", "other-profile", "other-context", "other-measurement", "null-source", "invalid-group", "zero-default", "bad-json"} {
		t.Run(mutation, func(t *testing.T) {
			data, _ := json.Marshal(valid)
			var envelope map[string]any
			_ = json.Unmarshal(data, &envelope)
			switch mutation {
			case "negative":
				envelope["costs"].(map[string]any)["cases"] = map[string]any{"unknown.case": -1}
			case "unaudited":
				envelope["audited"] = false
			case "other-profile":
				envelope["profile"] = "qualification"
			case "other-context":
				envelope["compatibility"] = "other"
			case "other-measurement":
				envelope["costs"].(map[string]any)["measurement"] = "assertions-only"
			case "null-source":
				envelope["source"] = nil
			case "invalid-group":
				envelope["costs"].(map[string]any)["groups"] = map[string]any{"recipe:base": map[string]any{"seconds": 0, "members": []string{"unknown.case"}}}
			case "zero-default":
				envelope["costs"].(map[string]any)["default_seconds"] = 0
			}
			data, _ = json.Marshal(envelope)
			if mutation == "bad-json" {
				data = []byte("{")
			}
			if err := os.WriteFile(path, data, 0600); err != nil {
				t.Fatal(err)
			}
			costs, source, err := restoredCosts(path, "regression", "context")
			if err != nil {
				t.Fatal(err)
			}
			if mutation == "valid" {
				if costs.DefaultSeconds != 23 || len(source) == 0 || costs.Cases["unknown.case"] != 12 {
					t.Fatal("compatible audited history was not restored")
				}
			} else if !reflect.DeepEqual(costs, fallback) || len(source) != 0 {
				t.Fatal("invalid history changed fallback or blocked current execution")
			}
		})
	}
}
func TestAPIQualificationPlanRequiresCurrentHuaweiCases(t *testing.T) {
	path := filepath.Join(t.TempDir(), "plan.json")
	if code := ciPlan([]string{"--profile", "qualification", "--revision", strings.Repeat("a", 40), "--backend-image", "sha256:image", "--output", path}); code != 0 {
		t.Fatalf("planning returned %d", code)
	}
	plan, err := loadRunPlan(path)
	if err != nil {
		t.Fatal(err)
	}
	var cloud []string
	for _, entry := range plan.Catalog {
		if entry.Capability == "huawei" {
			cloud = append(cloud, entry.ID)
		}
		if entry.Capability == "dnspod" || slices.Contains(entry.Tags, "mojang") {
			t.Fatal("implicit optional external provider in qualification")
		}
	}
	if !slices.Contains(cloud, "dns.huawei-minecraft-connectivity") || !slices.Contains(cloud, "dns.huawei-reconciliation") {
		t.Fatal("required real Huawei business cases absent")
	}
	if err = plan.Validate(currentCatalog(), "qualification"); err != nil {
		t.Fatal(err)
	}
	if plan.Validate(currentCatalog(), "regression") == nil {
		t.Fatal("protected cloud plan accepted in ordinary PR context")
	}
	shard := plan.Shards[0].Index
	privateConfig := filepath.Join(t.TempDir(), "external.json")
	if err = os.WriteFile(privateConfig, []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	if code := mainCode([]string{"plan", "--execution-plan", path, "--profile", "qualification", "--revision", "wrong", "--backend-image", "sha256:image", "--shard", fmt.Sprintf("%d/%d", shard, len(plan.Shards)), "--external-config", privateConfig}); code != 2 {
		t.Fatal("wrong source was not rejected before Docker access")
	}
	ordinary, _ := engine.ProfileCases(currentCatalog(), "regression")
	for _, test := range ordinary {
		if test.Capability != "" {
			t.Fatal("ordinary PR contains cloud capability")
		}
	}
}

func TestAPIPlanEmitsOneCompleteDependencyMatrix(t *testing.T) {
	for _, profile := range []string{"regression", "qualification", "dnspod"} {
		t.Run(profile, func(t *testing.T) {
			directory := t.TempDir()
			planPath, outputs := filepath.Join(directory, "plan.json"), filepath.Join(directory, "outputs")
			if err := os.WriteFile(outputs, nil, 0600); err != nil {
				t.Fatal(err)
			}
			if code := ciPlan([]string{"--profile", profile, "--revision", strings.Repeat("a", 40), "--backend-image", "sha256:image", "--output", planPath, "--github-output", outputs}); code != 0 {
				t.Fatalf("planning returned %d", code)
			}
			plan, err := loadRunPlan(planPath)
			if err != nil {
				t.Fatal(err)
			}
			data, err := os.ReadFile(outputs)
			if err != nil {
				t.Fatal(err)
			}
			lines := strings.Split(strings.TrimSpace(string(data)), "\n")
			if len(lines) != 2 || !strings.HasPrefix(lines[0], "matrix=") || lines[1] != "profile="+profile {
				t.Fatal("CLI emitted separate execution matrices or omitted the requested profile")
			}
			var matrix struct {
				Include []apiMatrixEntry `json:"include"`
			}
			if err = json.Unmarshal([]byte(strings.TrimPrefix(lines[0], "matrix=")), &matrix); err != nil {
				t.Fatal(err)
			}
			seen := map[string]bool{}
			if len(matrix.Include) != len(plan.Shards) {
				t.Fatal("matrix omits immutable plan shards")
			}
			for i, row := range matrix.Include {
				if row.Shard != i+1 || row.Count != len(plan.Shards) || row.Providers == nil {
					t.Fatal("matrix indices/count or explicit provider list differs from the complete plan")
				}
				var providers []string
				for _, entry := range plan.Catalog {
					if entry.Shard == row.Shard && entry.Capability != "" {
						providers = append(providers, entry.Capability)
					}
				}
				slices.Sort(providers)
				providers = slices.Compact(providers)
				if !slices.Equal(row.Providers, providers) {
					t.Fatal("provider union differs from the cases actually assigned to this shard")
				}
				wantEnvironment := ""
				if slices.Contains(providers, "huawei") {
					wantEnvironment = "dns-e2e"
				}
				if row.Environment != wantEnvironment {
					t.Fatal("protected environment differs from the shard's actual dependencies")
				}
				for _, id := range plan.Shards[i].Cases {
					if seen[id] {
						t.Fatal("matrix repeats a case")
					}
					seen[id] = true
				}
			}
			if len(seen) != len(plan.Catalog) {
				t.Fatal("matrix union omits current selected cases")
			}
		})
	}
}

func TestAPIMatrixMapsProviderDependenciesWithoutPartitioning(t *testing.T) {
	for _, row := range []struct {
		providers   []string
		environment string
	}{
		{[]string{}, ""},
		{[]string{"dnspod"}, ""},
		{[]string{"huawei"}, "dns-e2e"},
		{[]string{"dnspod", "huawei"}, "dns-e2e"},
	} {
		matrix, err := apiMatrix(engine.RunPlan{Shards: []engine.Shard{{Index: 1, Providers: row.providers}}})
		if err != nil {
			t.Fatal(err)
		}
		if len(matrix) != 1 || matrix[0].Shard != 1 || matrix[0].Count != 1 || matrix[0].Environment != row.environment || !slices.Equal(matrix[0].Providers, row.providers) {
			t.Fatal("resource dependencies created separate matrices or changed authorization mapping")
		}
	}
	if _, err := apiMatrix(engine.RunPlan{Shards: []engine.Shard{{Index: 1, Providers: []string{"huawei", "unmapped"}}}}); err == nil {
		t.Fatal("unknown provider received an implicit environment mapping")
	}
}

func TestAPIMixedShardRequiresPrivateConfigurationBeforeRuntime(t *testing.T) {
	path := filepath.Join(t.TempDir(), "plan.json")
	revision := strings.Repeat("a", 40)
	if code := ciPlan([]string{"--profile", "qualification", "--revision", revision, "--backend-image", "sha256:image", "--max-shards", "1", "--output", path}); code != 0 {
		t.Fatalf("planning returned %d", code)
	}
	plan, err := loadRunPlan(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Shards) != 1 || !slices.Equal(plan.Shards[0].Providers, []string{"huawei"}) {
		t.Fatal("mixed one-shard qualification lost its protected dependency")
	}
	if code := mainCode([]string{"plan", "--execution-plan", path, "--profile", "qualification", "--revision", revision, "--backend-image", "sha256:image", "--shard", "1/1"}); code != 2 {
		t.Fatal("mixed external dependency was not rejected before Docker access")
	}
}
