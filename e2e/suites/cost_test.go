package suites

import (
	"reflect"
	"testing"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func TestRegressionCostPlanCoversCatalogAndBalancesHistoricalWork(t *testing.T) {
	profile, err := Costs()
	if err != nil {
		t.Fatal(err)
	}
	if len(profile.Sources) < 2 || profile.Measurement == "" {
		t.Fatal("historical weights have no measurement provenance")
	}
	factory := fixtures.NewFactory(fixtures.Options{MinecraftSlots: 1}, nil, nil)
	catalog := Catalog(factory.Recipes())
	seen := map[string]bool{}
	var assignments []engine.Entry
	var work, minecraft [3]float64
	for shard := 1; shard <= 3; shard++ {
		plan, err := engine.BuildPlan(catalog, engine.Selection{Tag: "regression", ShardIndex: shard, ShardCount: 3, Costs: profile, Seed: 36155392209})
		if err != nil {
			t.Fatal(err)
		}
		if shard == 1 {
			assignments = plan.Catalog
		} else if !reflect.DeepEqual(assignments, plan.Catalog) {
			t.Fatal("independent shards produced incompatible assignments")
		}
		for _, id := range plan.Order {
			if seen[id] {
				t.Fatalf("duplicate case %s", id)
			}
			seen[id] = true
		}
	}
	for _, entry := range assignments {
		if !seen[entry.ID] {
			t.Fatalf("case %s missing from shard union", entry.ID)
		}
		work[entry.Shard-1] += entry.EstimatedSeconds
		minecraft[entry.Shard-1] += entry.EstimatedSeconds * float64(entry.MinecraftSlots)
	}
	if len(seen) != len(assignments) {
		t.Fatal("shard union contains unplanned cases")
	}
	for _, load := range [][3]float64{work, minecraft} {
		if max(load[0], load[1], load[2]) > 1.15*min(load[0], load[1], load[2]) {
			t.Fatalf("historical resource costs remain unbalanced: %v", load)
		}
	}
}
