package engine

import (
	"slices"
	"testing"
)

func timedCase(id string, isolation Isolation) Case {
	test := testCase(id, testRecipe(), isolation)
	test.Tags = []string{"regression"}
	return test
}
func timedInput() RunPlan {
	return RunPlan{Profile: "regression", Revision: "current", Image: "sha256:image", RunnerSHA256: "runner", Workers: 2, MinecraftSlots: 1, BudgetSeconds: 300, MaxShards: 16, Costs: CostProfile{Version: 1, DefaultSeconds: 30}}
}

func TestAutomaticPlanPreservesOversizedGroupsAndResourceLowerBound(t *testing.T) {
	ordinary := timedCase("case.oversized", Fresh)
	game := testRecipe()
	game.ID = "game"
	game.MinecraftSlots = 1
	cases := []Case{ordinary}
	input := timedInput()
	input.Costs.Cases = map[string]float64{"case.oversized": 450}
	for _, id := range []string{"case.game-a", "case.game-b", "case.game-c"} {
		test := testCase(id, game, Fresh)
		test.Tags = []string{"regression"}
		cases = append(cases, test)
		input.Costs.Cases[id] = 120
	}
	newCase := testCase("case.new", ordinary.Recipe, Fresh)
	newCase.Tags = []string{"regression"}
	cases = append(cases, newCase)
	plan, err := BuildRunPlan(cases, input)
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Catalog) != 5 || len(plan.Shards) != 3 || len(plan.Oversized) != 1 {
		t.Fatalf("unexpected bounded allocation: %+v", plan)
	}
	for _, shard := range plan.Shards {
		if slices.Contains(shard.Cases, "case.oversized") && (len(shard.Cases) != 1 || shard.EstimatedSeconds != 450) {
			t.Fatal("oversized case was divided or shared")
		}
		if !slices.Contains(shard.Cases, "case.oversized") && shard.EstimatedSeconds > 300 {
			t.Fatal("Minecraft sequential occupancy was underestimated")
		}
	}
	for _, entry := range plan.Catalog {
		if entry.ID == "case.new" && entry.EstimatedSeconds != 30 {
			t.Fatal("new case lost its positive fallback")
		}
	}
}

func TestAutomaticPlanBoundsWithoutDroppingAtomicGroups(t *testing.T) {
	recipe := testRecipe()
	a, b := testCase("case.a", recipe, ObserveReuse), testCase("case.b", recipe, CleanReuse)
	c := testCase("case.c", recipe, Fresh)
	for _, test := range []*Case{&a, &b, &c} {
		test.Tags = []string{"regression"}
	}
	input := timedInput()
	input.MaxShards = 1
	input.Costs.DefaultSeconds = 200
	plan, err := BuildRunPlan([]Case{a, b, c}, input)
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Catalog) != 3 || len(plan.Shards) != 1 || plan.Shards[0].EstimatedSeconds < 400 {
		t.Fatal("bounded plan dropped or divided its serial group")
	}
	execution, err := plan.Execution([]Case{a, b, c}, 1, "regression")
	if err != nil {
		t.Fatal(err)
	}
	if len(execution.Groups) != 2 || len(execution.Order) != 3 {
		t.Fatal("atomic reuse group lost at shard limit")
	}
	input.NoReuse = true
	input.MaxShards = 16
	fresh, err := BuildRunPlan([]Case{a, b, c}, input)
	if err != nil {
		t.Fatal(err)
	}
	if len(fresh.Shards) != 2 {
		t.Fatalf("Fresh worker capacity was ignored: %+v", fresh.Shards)
	}
	input.MaxShards = 1
	bounded, err := BuildRunPlan([]Case{a, b, c}, input)
	if err != nil {
		t.Fatal(err)
	}
	if len(bounded.Catalog) != 3 || len(bounded.Oversized) != 1 || bounded.Oversized[0].Reason != "shard_limit: maximum shard count retains all indivisible lifecycle groups" {
		t.Fatal("capacity-constrained Fresh groups lost their soft budget reason")
	}
}

func TestImmutableQualificationRejectsReducedOrChangedCatalog(t *testing.T) {
	recipe := testRecipe()
	a := testCase("case.normal", recipe, Fresh)
	a.Tags = []string{"regression"}
	b, c := testCase("case.cloud-a", recipe, Fresh), testCase("case.cloud-b", recipe, Fresh)
	b.Capability = "huawei"
	c.Capability = "huawei"
	b.Tags = []string{"external"}
	c.Tags = []string{"external"}
	cases := []Case{a, b, c}
	input := timedInput()
	input.Profile = "qualification"
	plan, err := BuildRunPlan(cases, input)
	if err != nil {
		t.Fatal(err)
	}
	if err = plan.Validate(cases, "qualification"); err != nil {
		t.Fatal(err)
	}
	if len(plan.Shards) != 2 {
		t.Fatal("ordinary and protected capabilities were mixed")
	}
	reduced, err := BuildRunPlan([]Case{a, b}, input)
	if err != nil {
		t.Fatal(err)
	}
	if reduced.Validate(cases, "qualification") == nil {
		t.Fatal("internally consistent reduced expected catalog qualified")
	}
	input.Profile = "regression"
	ordinary, err := BuildRunPlan(cases, input)
	if err != nil {
		t.Fatal(err)
	}
	if len(ordinary.Catalog) != 1 || ordinary.Validate(cases, "qualification") == nil {
		t.Fatal("ordinary PR plan satisfied trusted qualification")
	}
	plan.Catalog[0].EstimatedSeconds++
	if plan.Validate(cases, "qualification") == nil {
		t.Fatal("mutable history or assignment accepted")
	}
}

func TestReusableHistoryRetainsFixtureFloorAfterRemovingSetupMember(t *testing.T) {
	recipe := testRecipe()
	member := testCase("case.member", recipe, ObserveReuse)
	member.Tags = []string{"regression"}
	added := testCase("case.new", recipe, CleanReuse)
	added.Tags = []string{"regression"}
	input := timedInput()
	input.Costs.Cases = map[string]float64{"case.member": 20, "case.setup": 260}
	input.Costs.Groups = map[string]GroupCost{"recipe:base": {Seconds: 280, Members: []string{"case.setup", "case.member"}}}
	plan, err := BuildRunPlan([]Case{member}, input)
	if err != nil {
		t.Fatal(err)
	}
	if plan.Shards[0].EstimatedSeconds != 280 {
		t.Fatal("removing setup-bearing case lost reusable fixture lifecycle")
	}
	plan, err = BuildRunPlan([]Case{member, added}, input)
	if err != nil {
		t.Fatal(err)
	}
	if plan.Shards[0].EstimatedSeconds != 310 || len(plan.Shards) != 1 || len(plan.Oversized) != 1 {
		t.Fatal("new member fallback omitted or serial group divided by worker count")
	}
}

func TestAutomaticPlanIncludesFixedLifecycleOverhead(t *testing.T) {
	first := timedCase("case.one", Fresh)
	second := testCase("case.two", first.Recipe, Fresh)
	second.Tags = []string{"regression"}
	cases := []Case{first, second}
	input := timedInput()
	input.Costs.ShardOverheadSeconds = 320
	plan, err := BuildRunPlan(cases, input)
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Shards) != 1 || plan.Shards[0].EstimatedSeconds != 350 || len(plan.Oversized) != 1 || plan.Oversized[0].Key != "fixed-overhead" {
		t.Fatal("fixed setup/final cleanup overhead was omitted or endlessly split")
	}
}
