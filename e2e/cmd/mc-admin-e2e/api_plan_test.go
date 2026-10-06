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
func TestAPIProfilesRequireAllCurrentCasesExceptDNSPod(t *testing.T) {
	for _, profile := range []string{"regression", "qualification"} {
		t.Run(profile, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "plan.json")
			if code := ciPlan([]string{"--profile", profile, "--revision", strings.Repeat("a", 40), "--backend-image", "sha256:image", "--output", path}); code != 0 {
				t.Fatalf("planning returned %d", code)
			}
			plan, err := loadRunPlan(path)
			if err != nil {
				t.Fatal(err)
			}
			wanted := map[string]bool{}
			for _, test := range currentCatalog() {
				if test.Capability != "dnspod" {
					wanted[test.ID] = true
				}
			}
			for _, entry := range plan.Catalog {
				if !wanted[entry.ID] {
					t.Fatalf("unexpected or duplicate current case %s", entry.ID)
				}
				delete(wanted, entry.ID)
			}
			if len(wanted) != 0 {
				t.Fatalf("current cases missing from profile: %v", wanted)
			}
			if err = plan.Validate(currentCatalog(), profile); err != nil {
				t.Fatal(err)
			}
			other := "regression"
			if profile == other {
				other = "qualification"
			}
			if plan.Validate(currentCatalog(), other) == nil {
				t.Fatal("plan accepted a different required profile")
			}
			shard := plan.Shards[0].Index
			privateConfig := filepath.Join(t.TempDir(), "external.json")
			if err = os.WriteFile(privateConfig, []byte("{}"), 0600); err != nil {
				t.Fatal(err)
			}
			if code := mainCode([]string{"plan", "--execution-plan", path, "--profile", profile, "--revision", "wrong", "--backend-image", "sha256:image", "--shard", fmt.Sprintf("%d/%d", shard, len(plan.Shards)), "--external-config", privateConfig}); code != 2 {
				t.Fatal("wrong source was not rejected before Docker access")
			}
		})
	}
}

func TestAPIPlanRejectsUnsupportedCIProfiles(t *testing.T) {
	for _, profile := range []string{"smoke", "mojang", "unknown"} {
		t.Run(profile, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "plan.json")
			if code := ciPlan([]string{"--profile", profile, "--revision", strings.Repeat("a", 40), "--backend-image", "sha256:image", "--output", path}); code != 2 {
				t.Fatalf("unsupported CI profile returned %d", code)
			}
			if _, err := os.Stat(path); !os.IsNotExist(err) {
				t.Fatalf("unsupported profile wrote an executable plan: %v", err)
			}
		})
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
			var fields struct {
				Include []map[string]json.RawMessage `json:"include"`
			}
			if err = json.Unmarshal([]byte(strings.TrimPrefix(lines[0], "matrix=")), &fields); err != nil {
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
				if _, exists := fields.Include[i]["environment"]; exists {
					t.Fatal("matrix emits an environment authorization binding")
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

func TestAPIMatrixPreservesProviderDependenciesWithoutPartitioning(t *testing.T) {
	for _, providers := range [][]string{
		{},
		{"dnspod"},
		{"huawei"},
		{"dnspod", "huawei"},
		{"huawei", "other-provider"},
	} {
		matrix := apiMatrix(engine.RunPlan{Shards: []engine.Shard{{Index: 1, Providers: providers}}})
		if len(matrix) != 1 || matrix[0].Shard != 1 || matrix[0].Count != 1 || matrix[0].Providers == nil || !slices.Equal(matrix[0].Providers, providers) {
			t.Fatal("resource dependencies created separate matrices or lost provider metadata")
		}
	}
}

func TestAPIMixedShardRequiresPrivateConfigurationBeforeRuntime(t *testing.T) {
	for _, profile := range []string{"regression", "qualification"} {
		t.Run(profile, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "plan.json")
			revision := strings.Repeat("a", 40)
			if code := ciPlan([]string{"--profile", profile, "--revision", revision, "--backend-image", "sha256:image", "--max-shards", "1", "--output", path}); code != 0 {
				t.Fatalf("planning returned %d", code)
			}
			plan, err := loadRunPlan(path)
			if err != nil {
				t.Fatal(err)
			}
			var providers []string
			for _, entry := range plan.Catalog {
				if entry.Capability != "" {
					providers = append(providers, entry.Capability)
				}
			}
			slices.Sort(providers)
			providers = slices.Compact(providers)
			if len(plan.Shards) != 1 || !slices.Equal(plan.Shards[0].Providers, providers) {
				t.Fatal("mixed one-shard plan lost its declared provider dependencies")
			}
			if len(providers) > 0 && mainCode([]string{"plan", "--execution-plan", path, "--profile", profile, "--revision", revision, "--backend-image", "sha256:image", "--shard", "1/1"}) != 2 {
				t.Fatal("mixed external dependency was not rejected before Docker access")
			}
		})
	}
}
