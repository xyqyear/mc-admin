package engine

import (
	"math"
	"reflect"
	"slices"
	"testing"
)

func TestWeightedPlanBalancesResourcesAndKeepsGroupsAtomic(t *testing.T) {
	game, ordinary := testRecipe(), testRecipe()
	game.ID, game.MinecraftSlots = "game", 1
	profile := CostProfile{Version: 1, DefaultSeconds: 30, Recipes: map[string]float64{"base": 20}, Cases: map[string]float64{"case.a": 120, "case.b": 100, "case.c": 80, "case.d": 40, "case.e": 40, "case.f": 40}}
	cases := []Case{testCase("case.a", game, Fresh), testCase("case.b", game, Fresh), testCase("case.c", game, Fresh), testCase("case.d", ordinary, Fresh), testCase("case.e", ordinary, Fresh), testCase("case.f", ordinary, Fresh), testCase("case.new", ordinary, ObserveReuse), testCase("case.reuse", ordinary, CleanReuse)}
	seen := map[string]int{}
	var catalog []Entry
	for shard := 1; shard <= 3; shard++ {
		selection := Selection{ShardIndex: shard, ShardCount: 3, Seed: 42, Costs: profile}
		plan, err := BuildPlan(cases, selection)
		if err != nil {
			t.Fatal(err)
		}
		reversed := slices.Clone(cases)
		slices.Reverse(reversed)
		reordered, err := BuildPlan(reversed, selection)
		if err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(plan.Catalog, reordered.Catalog) || !reflect.DeepEqual(plan.Order, reordered.Order) {
			t.Fatal("input order changes weighted plan")
		}
		selection.Seed = 91
		shuffled, err := BuildPlan(cases, selection)
		if err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(plan.Catalog, shuffled.Catalog) {
			t.Fatal("seed changed shard membership")
		}
		if shard == 1 {
			catalog = plan.Catalog
		} else if !reflect.DeepEqual(catalog, plan.Catalog) {
			t.Fatal("shards disagree about full assignment")
		}
		var gameCount int
		for _, entry := range plan.Catalog {
			if entry.Shard == shard && entry.MinecraftSlots > 0 {
				gameCount++
			}
			if entry.ID == "case.new" && entry.EstimatedSeconds != 20 {
				t.Fatal("new case did not use recipe fallback")
			}
		}
		if gameCount != 1 {
			t.Fatal("heavy Minecraft cases were not distributed")
		}
		for _, id := range plan.Order {
			seen[id]++
		}
	}
	if len(seen) != len(cases) {
		t.Fatal("new or existing case lost")
	}
	for id, count := range seen {
		if count != 1 {
			t.Fatalf("case %s occurs %d times", id, count)
		}
	}
	var reuseShard int
	for _, entry := range catalog {
		if entry.Isolation != Fresh {
			if reuseShard != 0 && entry.Shard != reuseShard {
				t.Fatal("reuse group split")
			}
			reuseShard = entry.Shard
		}
	}
}

func TestCostProfileValidationAndIdentity(t *testing.T) {
	cases := []Case{testCase("case.one", testRecipe(), Fresh)}
	for _, cost := range []float64{0, -1, math.NaN(), math.Inf(1)} {
		_, err := BuildPlan(cases, Selection{ShardIndex: 1, ShardCount: 1, Costs: CostProfile{Version: 1, DefaultSeconds: 30, Cases: map[string]float64{"case.one": cost}}})
		if err == nil {
			t.Fatalf("invalid cost %v accepted", cost)
		}
	}
	selection := Selection{ShardIndex: 1, ShardCount: 1, Costs: CostProfile{Version: 1, DefaultSeconds: 30}}
	first, err := BuildPlan(cases, selection)
	if err != nil {
		t.Fatal(err)
	}
	selection.Costs.DefaultSeconds = 60
	second, err := BuildPlan(cases, selection)
	if err != nil {
		t.Fatal(err)
	}
	if first.Scheduling.CostSHA256 == second.Scheduling.CostSHA256 || second.Catalog[0].EstimatedSeconds != 60 {
		t.Fatal("cost change not visible in plan identity")
	}
}
