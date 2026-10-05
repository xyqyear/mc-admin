package coverage

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"sort"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/platform"
)

func AuditExpected(runDirs []string, expected engine.RunPlan, catalog []engine.Case, requiredProfile string) (engine.CostProfile, error) {
	if err := expected.Validate(catalog, requiredProfile); err != nil {
		return engine.CostProfile{}, err
	}
	if len(runDirs) != len(expected.Shards) {
		return engine.CostProfile{}, fmt.Errorf("missing or unexpected API shard reports")
	}
	costs := engine.CostProfile{Version: 1, Measurement: "api-lifecycle-v2", DefaultSeconds: expected.Costs.DefaultSeconds, Recipes: expected.Costs.Recipes, Cases: map[string]float64{}, Groups: map[string]engine.GroupCost{}}
	seen := map[int]bool{}
	for _, dir := range runDirs {
		var report engine.Report
		if err := readJSON(filepath.Join(dir, "results.json"), &report); err != nil {
			return costs, err
		}
		actual, err := expected.Execution(catalog, report.Plan.ShardIndex, requiredProfile)
		if err != nil {
			return costs, err
		}
		actual.Groups = nil
		if !reflect.DeepEqual(actual, report.Plan) || seen[actual.ShardIndex] || report.Image != expected.Image || report.NoReuse != expected.NoReuse || report.Failed() {
			return costs, fmt.Errorf("API shard identity, assignments or outcomes differ from expected plan")
		}
		seen[actual.ShardIndex] = true
		var recovery struct {
			Seconds float64 `json:"seconds"`
		}
		if err = readJSON(filepath.Join(dir, "recovery.json"), &recovery); err != nil {
			return costs, err
		}
		if recovery.Seconds < 0 || math.IsNaN(recovery.Seconds) || math.IsInf(recovery.Seconds, 0) {
			return costs, fmt.Errorf("invalid unconditional recovery measurement")
		}
		for _, overhead := range []float64{report.PreparationSeconds, report.CleanupSeconds} {
			if overhead < 0 || math.IsNaN(overhead) || math.IsInf(overhead, 0) {
				return costs, fmt.Errorf("invalid runner lifecycle overhead")
			}
		}
		costs.ShardOverheadSeconds = max(costs.ShardOverheadSeconds, report.CleanupSeconds+recovery.Seconds)
		var manifest platform.Manifest
		if err = readJSON(filepath.Join(dir, "manifest.json"), &manifest); err != nil {
			return costs, err
		}
		if manifest.Version != 1 || manifest.RunID != report.RunID || manifest.Image != expected.Image || len(manifest.Environments) == 0 {
			return costs, fmt.Errorf("missing candidate-bound owned cleanup evidence")
		}
		clean := map[string]bool{}
		for _, env := range manifest.Environments {
			if env == nil || !env.Cleaned || clean[env.ID] {
				return costs, fmt.Errorf("owned environment cleanup is incomplete or duplicated")
			}
			clean[env.ID] = true
		}
		resultIDs := map[string]bool{}
		assigned := map[string]engine.Entry{}
		for _, entry := range expected.Catalog {
			if entry.Shard == actual.ShardIndex {
				assigned[entry.ID] = entry
			}
		}
		for _, result := range report.Results {
			entry, exists := assigned[result.ID]
			if !exists || resultIDs[result.ID] || !clean[result.Environment] || len(result.Issues) > 0 {
				return costs, fmt.Errorf("case or environment differs from exact assignment")
			}
			resultIDs[result.ID] = true
			timings := result.Timings
			phases := []float64{timings.SetupSeconds, timings.AssertionSeconds, timings.CaseCleanupSeconds, timings.VerificationSeconds, timings.DiagnosticsSeconds, timings.TeardownSeconds}
			measured := 0.0
			for _, value := range phases {
				if value < 0 || math.IsNaN(value) || math.IsInf(value, 0) {
					return costs, fmt.Errorf("invalid lifecycle measurement")
				}
				measured += value
			}
			if measured <= 0 {
				return costs, fmt.Errorf("missing lifecycle measurement for %s", result.ID)
			}
			costs.Cases[result.ID] = measured
			key := "recipe:" + entry.Recipe
			if entry.Isolation == engine.Fresh || expected.NoReuse {
				key = "case:" + entry.ID
			}
			group := costs.Groups[key]
			group.Seconds += measured
			group.Members = append(group.Members, result.ID)
			costs.Groups[key] = group
			if entry.Capability == "huawei" || entry.Capability == "dnspod" {
				var cleanup cloudCleanup
				if err = readJSON(filepath.Join(dir, "cloud", result.Environment+".json"), &cleanup); err != nil {
					return costs, err
				}
				if cleanup.Version != 1 || cleanup.Provider != entry.Capability || cleanup.RunID != report.RunID || cleanup.Environment != result.Environment || !cleanup.Armed || !cleanup.Cleaned {
					return costs, fmt.Errorf("external cleanup is incomplete or differs from its case/environment")
				}
			}
		}
		if len(resultIDs) != len(assigned) {
			return costs, fmt.Errorf("API shard omits assigned cases")
		}
	}
	if len(costs.Cases) != len(expected.Catalog) {
		return costs, fmt.Errorf("current API inventory is incomplete")
	}
	sort.Strings(costs.Sources)
	for key, group := range costs.Groups {
		sort.Strings(group.Members)
		costs.Groups[key] = group
	}
	return costs, nil
}

func readJSON(path string, target any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, target)
}
