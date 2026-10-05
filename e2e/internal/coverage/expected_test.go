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

func expectedFixture(t *testing.T) (engine.RunPlan, []engine.Case, []string) {
	t.Helper()
	recipe := &environment.Recipe{ID: "base", Providers: []environment.Provider{{ID: "base", Setup: func(context.Context, *environment.Environment) error { return nil }}}}
	ordinary := engine.Case{ID: "case.normal", Suite: "test", Tags: []string{"regression"}, Recipe: recipe, Isolation: engine.Fresh, Timeout: time.Second, Run: func(context.Context, *engine.Scope) error { return nil }}
	cloud := ordinary
	cloud.ID = "case.cloud"
	cloud.Tags = []string{"external"}
	cloud.Capability = "huawei"
	catalog := []engine.Case{ordinary, cloud}
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
		envID := "012345abcdef"
		if shard.Capability == "ordinary" {
			envID = "abcdef012345"
		}
		report := engine.Report{RunID: "run-" + envID, Image: expected.Image, Plan: plan, PreparationSeconds: 3, CleanupSeconds: 2}
		for _, id := range plan.Order {
			report.Results = append(report.Results, engine.Result{ID: id, Suite: "test", Environment: envID, Status: "passed", Timings: engine.Timings{SetupSeconds: 5, AssertionSeconds: 7, CaseCleanupSeconds: 4, TeardownSeconds: 2, ReservationSeconds: 500, SchedulerQueueSeconds: 600}})
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
		write("manifest.json", platform.Manifest{Version: 1, RunID: report.RunID, Image: expected.Image, Environments: []*platform.EnvironmentRecord{{ID: envID, Cleaned: true}}})
		write("recovery.json", map[string]any{"seconds": 1})
		if shard.Capability == "huawei" {
			if err = os.Mkdir(filepath.Join(dir, "cloud"), 0700); err != nil {
				t.Fatal(err)
			}
			scope := map[string]any{"version": 1, "provider": "huawei", "environment": envID, "run_id": report.RunID, "domain": "test.invalid", "scope": "run-" + envID, "helper": "mca-dns-helper-" + envID, "armed": true, "cleaned": true}
			write("cloud/"+envID+".json", scope)
			initial, _ := json.Marshal(map[string]any{"kind": "external_dns_scope", "data": scope})
			cleanup, _ := json.Marshal(map[string]any{"kind": "external_dns_cleanup", "data": map[string]any{"manifest": scope}})
			if err = os.WriteFile(filepath.Join(dir, "cases", "case.cloud.jsonl"), append(append(initial, byte(10)), append(cleanup, byte(10))...), 0600); err != nil {
				t.Fatal(err)
			}
		}
		dirs = append(dirs, dir)
	}
	return expected, catalog, dirs
}
func TestExpectedAuditRequiresExactCloudCleanupAndLifecycleEvidence(t *testing.T) {
	expected, catalog, dirs := expectedFixture(t)
	costs, err := AuditExpected(dirs, expected, catalog, "qualification")
	if err != nil {
		t.Fatal(err)
	}
	if costs.Cases["case.cloud"] != 18 || costs.ShardOverheadSeconds != 3 {
		t.Fatalf("queue counted or fixture/cloud cleanup omitted: %+v", costs)
	}
	if _, err = AuditExpected(dirs[:1], expected, catalog, "qualification"); err == nil {
		t.Fatal("missing cloud shard qualified")
	}
	for _, mutation := range []string{"missing", "unclean", "wrong-environment", "wrong-domain", "wrong-scope", "extra"} {
		t.Run(mutation, func(t *testing.T) {
			expected, catalog, dirs := expectedFixture(t)
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
				case "wrong-environment":
					scope["environment"] = "111111111111"
				case "wrong-domain":
					scope["domain"] = "other.invalid"
				case "wrong-scope":
					scope["scope"] = "unrelated-prefix"
				case "extra":
					_ = os.WriteFile(filepath.Join(dir, "cloud", "extra.json"), data, 0600)
				}
				if mutation != "missing" {
					data, _ = json.Marshal(scope)
					_ = os.WriteFile(path, data, 0600)
				}
			}
			if _, err := AuditExpected(dirs, expected, catalog, "qualification"); err == nil {
				t.Fatal("unsafe cloud evidence qualified")
			}
		})
	}
}
func TestExpectedAuditRejectsChangedPlanAndFailedRecovery(t *testing.T) {
	for _, mutation := range []string{"digest", "duplicate-case", "cleanup", "recovery"} {
		t.Run(mutation, func(t *testing.T) {
			expected, catalog, dirs := expectedFixture(t)
			path := filepath.Join(dirs[0], "results.json")
			if mutation == "recovery" {
				_ = os.Remove(filepath.Join(dirs[0], "recovery.json"))
			} else if mutation == "cleanup" {
				data, _ := os.ReadFile(filepath.Join(dirs[0], "manifest.json"))
				var manifest platform.Manifest
				_ = json.Unmarshal(data, &manifest)
				manifest.Environments[0].Cleaned = false
				data, _ = json.Marshal(manifest)
				_ = os.WriteFile(filepath.Join(dirs[0], "manifest.json"), data, 0600)
			} else {
				data, _ := os.ReadFile(path)
				var report engine.Report
				_ = json.Unmarshal(data, &report)
				if mutation == "digest" {
					report.Plan.Digest = "other"
				} else {
					report.Results = append(report.Results, report.Results[0])
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
