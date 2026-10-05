package coverage

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/platform"
)

func expectedFixture(t *testing.T, cloudIsolation engine.Isolation) (engine.RunPlan, []engine.Case, []string) {
	t.Helper()
	recipe := &environment.Recipe{ID: "base", Providers: []environment.Provider{{ID: "base", Setup: func(context.Context, *environment.Environment) error { return nil }, Verify: func(context.Context, *environment.Environment) error { return nil }}}}
	ordinary := engine.Case{ID: "case.normal", Suite: "test", Tags: []string{"regression"}, Recipe: recipe, Isolation: engine.Fresh, Timeout: time.Second, Run: func(context.Context, *engine.Scope) error { return nil }}
	cloud := ordinary
	cloud.ID = "case.cloud"
	cloud.Tags = []string{"external"}
	cloud.Capability = "huawei"
	cloud.Isolation = cloudIsolation
	secondCloud := cloud
	secondCloud.ID = "case.cloud-second"
	catalog := []engine.Case{ordinary, cloud, secondCloud}
	environments := map[string]string{"case.normal": "abcdef012345", "case.cloud": "012345abcdef", "case.cloud-second": "abcd1234abcd"}
	if cloudIsolation != engine.Fresh {
		environments[secondCloud.ID] = environments[cloud.ID]
	}
	expected, err := engine.BuildRunPlan(catalog, engine.RunPlan{Profile: "qualification", Revision: "current", Image: "sha256:image", RunnerSHA256: "runner", Workers: 2, MinecraftSlots: 1, BudgetSeconds: 300, MaxShards: 16, Costs: engine.CostProfile{Version: 1, DefaultSeconds: 30}})
	if err != nil {
		t.Fatal(err)
	}
	var dirs []string
	for _, shard := range expected.Shards {
		plan, err := expected.Execution(catalog, shard.Index, "qualification")
		if err != nil {
			t.Fatal(err)
		}
		report := engine.Report{RunID: "run-mixed-qualification", Image: expected.Image, Plan: plan, PreparationSeconds: 3, CleanupSeconds: 2}
		var owned []*platform.EnvironmentRecord
		ownedEnvironments := map[string]bool{}
		for _, id := range plan.Order {
			envID := environments[id]
			report.Results = append(report.Results, engine.Result{ID: id, Suite: "test", Environment: envID, Status: "passed", Timings: engine.Timings{SetupSeconds: 5, AssertionSeconds: 7, CaseCleanupSeconds: 4, TeardownSeconds: 2, ReservationSeconds: 500, SchedulerQueueSeconds: 600}})
			if !ownedEnvironments[envID] {
				owned = append(owned, &platform.EnvironmentRecord{ID: envID, Cleaned: true})
				ownedEnvironments[envID] = true
			}
		}
		dir := runFixture(t, t.TempDir(), report.RunID, report, schemaFixture, map[string]string{})
		write := func(name string, value any) {
			t.Helper()
			data, err := json.Marshal(value)
			if err != nil {
				t.Fatal(err)
			}
			if err = os.WriteFile(filepath.Join(dir, name), data, 0600); err != nil {
				t.Fatal(err)
			}
		}
		write("manifest.json", platform.Manifest{Version: 1, RunID: report.RunID, Image: expected.Image, Environments: owned})
		write("recovery.json", map[string]any{"seconds": 1})
		for _, result := range report.Results {
			if result.ID == ordinary.ID {
				continue
			}
			if err = os.MkdirAll(filepath.Join(dir, "cloud"), 0700); err != nil {
				t.Fatal(err)
			}
			envID := result.Environment
			write("cloud/"+envID+".json", cloudCleanup{Version: 1, Provider: "huawei", Environment: envID, RunID: report.RunID, Armed: true, Cleaned: true})
		}
		dirs = append(dirs, dir)
	}
	return expected, catalog, dirs
}
func TestExpectedAuditRequiresCloudCleanupAndLifecycleEvidence(t *testing.T) {
	expected, catalog, dirs := expectedFixture(t, engine.Fresh)
	costs, err := AuditExpected(dirs, expected, catalog, "qualification")
	if err != nil {
		t.Fatal(err)
	}
	if costs.Cases["case.cloud"] != 18 || costs.ShardOverheadSeconds != 3 {
		t.Fatalf("queue counted or fixture/cloud cleanup omitted: %+v", costs)
	}
	if len(expected.Shards) != 1 || len(costs.Cases) != 3 {
		t.Fatal("mixed shard did not qualify all ordinary and cloud cases")
	}
	if _, err = AuditExpected(dirs[:len(dirs)-1], expected, catalog, "qualification"); err == nil {
		t.Fatal("missing API shard qualified")
	}
	for _, mutation := range []string{"missing", "unclean", "unarmed", "wrong-environment", "wrong-provider", "wrong-run", "unknown-version"} {
		t.Run(mutation, func(t *testing.T) {
			expected, catalog, dirs := expectedFixture(t, engine.Fresh)
			for _, dir := range dirs {
				files, _ := filepath.Glob(filepath.Join(dir, "cloud", "*.json"))
				if len(files) == 0 {
					continue
				}
				path := files[0]
				data, _ := os.ReadFile(path)
				var scope map[string]any
				_ = json.Unmarshal(data, &scope)
				switch mutation {
				case "missing":
					_ = os.Remove(path)
				case "unclean":
					scope["cleaned"] = false
				case "unarmed":
					scope["armed"] = false
				case "wrong-environment":
					scope["environment"] = "111111111111"
				case "wrong-provider":
					scope["provider"] = "dnspod"
				case "wrong-run":
					scope["run_id"] = "other-run"
				case "unknown-version":
					scope["version"] = 0
				}
				if mutation != "missing" {
					data, _ = json.Marshal(scope)
					_ = os.WriteFile(path, data, 0600)
				}
			}
			if _, err := AuditExpected(dirs, expected, catalog, "qualification"); err == nil {
				t.Fatal("missing or incomplete cloud cleanup qualified")
			}
		})
	}
}

func TestExpectedAuditAllowsReusableCloudEnvironments(t *testing.T) {
	expected, catalog, dirs := expectedFixture(t, engine.CleanReuse)
	costs, err := AuditExpected(dirs, expected, catalog, "qualification")
	if err != nil {
		t.Fatal(err)
	}
	if len(costs.Cases) != 3 || costs.Groups["recipe:base"].Seconds != 36 || len(costs.Groups["recipe:base"].Members) != 2 {
		t.Fatal("cloud environment reuse lost cases or lifecycle measurements")
	}
}

func TestExpectedAuditDoesNotRequireCloudAuthorizationReceipts(t *testing.T) {
	expected, catalog, dirs := expectedFixture(t, engine.Fresh)
	for _, dir := range dirs {
		paths, err := filepath.Glob(filepath.Join(dir, "cloud", "*.json"))
		if err != nil {
			t.Fatal(err)
		}
		for _, path := range paths {
			data, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			var manifest map[string]any
			if err = json.Unmarshal(data, &manifest); err != nil {
				t.Fatal(err)
			}
			manifest["domain"] = "other.invalid"
			manifest["scope"] = "shared.namespace"
			manifest["helper"] = "custom-helper"
			data, err = json.Marshal(manifest)
			if err != nil {
				t.Fatal(err)
			}
			if err = os.WriteFile(path, data, 0600); err != nil {
				t.Fatal(err)
			}
		}
	}
	if _, err := AuditExpected(dirs, expected, catalog, "qualification"); err != nil {
		t.Fatal(err)
	}
}

func TestExpectedAuditRejectsChangedPlanAndFailedRecovery(t *testing.T) {
	for _, mutation := range []string{"digest", "duplicate-case", "unknown-environment", "missing-cloud-case", "duplicate-environment", "cleanup", "recovery"} {
		t.Run(mutation, func(t *testing.T) {
			expected, catalog, dirs := expectedFixture(t, engine.Fresh)
			path := filepath.Join(dirs[0], "results.json")
			if mutation == "recovery" {
				_ = os.Remove(filepath.Join(dirs[0], "recovery.json"))
			} else if mutation == "cleanup" || mutation == "duplicate-environment" {
				data, _ := os.ReadFile(filepath.Join(dirs[0], "manifest.json"))
				var manifest platform.Manifest
				_ = json.Unmarshal(data, &manifest)
				if mutation == "cleanup" {
					manifest.Environments[0].Cleaned = false
				} else {
					manifest.Environments = append(manifest.Environments, manifest.Environments[0])
				}
				data, _ = json.Marshal(manifest)
				_ = os.WriteFile(filepath.Join(dirs[0], "manifest.json"), data, 0600)
			} else {
				data, _ := os.ReadFile(path)
				var report engine.Report
				_ = json.Unmarshal(data, &report)
				if mutation == "digest" {
					report.Plan.Digest = "other"
				} else if mutation == "duplicate-case" {
					report.Results = append(report.Results, report.Results[0])
				} else {
					for i, result := range report.Results {
						if result.ID == "case.cloud-second" {
							if mutation == "unknown-environment" {
								report.Results[i].Environment = "unknown-environment"
							} else {
								report.Results = append(report.Results[:i], report.Results[i+1:]...)
							}
							break
						}
					}
				}
				data, _ = json.Marshal(report)
				_ = os.WriteFile(path, data, 0600)
			}
			if _, err := AuditExpected(dirs, expected, catalog, "qualification"); err == nil {
				t.Fatal("altered or incomplete evidence qualified")
			}
		})
	}
}
