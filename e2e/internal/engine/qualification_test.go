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

func TestRegressionAndQualificationSelectAllCasesExceptDNSPod(t *testing.T) {
	recipe := testRecipe()
	var catalog []Case
	for _, entry := range []struct {
		id         string
		capability string
		tags       []string
	}{
		{"case.normal", "", []string{"smoke"}},
		{"case.huawei", "huawei", []string{"external", "dns"}},
		{"case.mojang", "", []string{"external", "mojang"}},
		{"case.future", "new-provider", []string{"external"}},
		{"case.untagged", "", nil},
		{"case.dnspod", "dnspod", []string{"external", "regression"}},
	} {
		test := testCase(entry.id, recipe, Fresh)
		test.Capability, test.Tags = entry.capability, entry.tags
		catalog = append(catalog, test)
	}
	for _, profile := range []string{"regression", "qualification"} {
		t.Run(profile, func(t *testing.T) {
			selected, err := ProfileCases(catalog, profile)
			if err != nil {
				t.Fatal(err)
			}
			var ids []string
			for _, test := range selected {
				ids = append(ids, test.ID)
			}
			if !slices.Equal(ids, []string{"case.normal", "case.huawei", "case.mojang", "case.future", "case.untagged"}) {
				t.Fatalf("profile omitted or added a current case: %v", ids)
			}
			selected, err = ProfileCases(catalog[:1], profile)
			if err != nil || len(selected) != 1 || selected[0].ID != "case.normal" {
				t.Fatalf("profile requires a named provider: %v, %v", selected, err)
			}
			for _, empty := range [][]Case{nil, catalog[5:]} {
				if _, err := ProfileCases(empty, profile); err == nil {
					t.Fatal("profile accepted an empty eligible inventory")
				}
			}
		})
	}
	selected, err := ProfileCases(catalog, "dnspod")
	if err != nil || len(selected) != 1 || selected[0].ID != "case.dnspod" {
		t.Fatalf("explicit DNSPod profile selected unintended cases: %v, %v", selected, err)
	}
	for _, profile := range []string{"smoke", "mojang", "unknown"} {
		if _, err := ProfileCases(catalog, profile); err == nil {
			t.Fatalf("unsupported CI profile %s accepted", profile)
		}
	}
}

func TestLocalTagSelectionPreservesExplicitCaseFilters(t *testing.T) {
	recipe := testRecipe()
	ordinary, external, other := testCase("case.smoke", recipe, Fresh), testCase("case.profile", recipe, Fresh), testCase("case.other", recipe, Fresh)
	ordinary.Tags = []string{"smoke", "regression"}
	external.Tags = []string{"external", "mojang", "regression"}
	other.Tags, other.Suite = []string{"external", "mojang", "regression"}, "other"
	for _, selection := range []struct {
		tag, match, wanted string
	}{
		{"smoke", "^case\\.smoke$", ordinary.ID},
		{"mojang", "^case\\.(profile|other)$", external.ID},
	} {
		plan, err := BuildPlan([]Case{ordinary, external, other}, Selection{Tag: selection.tag, Suite: "test", Match: selection.match, ShardIndex: 1, ShardCount: 1})
		if err != nil {
			t.Fatal(err)
		}
		if !slices.Equal(plan.Order, []string{selection.wanted}) {
			t.Fatalf("local %s filter selected unintended cases: %v", selection.tag, plan.Order)
		}
	}
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
	c.Capability = "new-provider"
	b.Tags = []string{"external"}
	c.Tags = []string{"external"}
	d := testCase("case.mojang", recipe, Fresh)
	d.Tags = []string{"external", "mojang"}
	cases := []Case{a, b, c, d}
	input := timedInput()
	input.Profile = "qualification"
	input.MaxShards = 1
	plan, err := BuildRunPlan(cases, input)
	if err != nil {
		t.Fatal(err)
	}
	if err = plan.Validate(cases, "qualification"); err != nil {
		t.Fatal(err)
	}
	if len(plan.Shards) != 1 || !slices.Equal(plan.Shards[0].Providers, []string{"huawei", "new-provider"}) {
		t.Fatal("mixed dependencies forced separate shards or lost their provider union")
	}
	for omitted := range cases {
		reducedCatalog := slices.Delete(slices.Clone(cases), omitted, omitted+1)
		reduced, err := BuildRunPlan(reducedCatalog, input)
		if err != nil {
			t.Fatal(err)
		}
		if reduced.Validate(cases, "qualification") == nil {
			t.Fatalf("internally consistent catalog omitting %s qualified", cases[omitted].ID)
		}
	}
	input.Profile = "regression"
	ordinary, err := BuildRunPlan(cases, input)
	if err != nil {
		t.Fatal(err)
	}
	if !slices.EqualFunc(ordinary.Catalog, plan.Catalog, func(left, right Entry) bool { return left.ID == right.ID && left.Capability == right.Capability }) {
		t.Fatal("regression and qualification selected different current inventories")
	}
	if ordinary.Validate(cases, "qualification") == nil {
		t.Fatal("plan accepted a different required profile")
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
	second.Tags = []string{"external"}
	second.Capability = "huawei"
	cases := []Case{first, second}
	for _, overhead := range []float64{20, 320} {
		input := timedInput()
		input.Profile = "qualification"
		input.Costs.ShardOverheadSeconds = overhead
		plan, err := BuildRunPlan(cases, input)
		if err != nil {
			t.Fatal(err)
		}
		if len(plan.Shards) != 1 || plan.Shards[0].EstimatedSeconds != overhead+30 || !slices.Equal(plan.Shards[0].Providers, []string{"huawei"}) {
			t.Fatal("fixed setup/final cleanup overhead was omitted or provider dependencies divided one global bin")
		}
		if overhead < input.BudgetSeconds && len(plan.Oversized) != 0 || overhead >= input.BudgetSeconds && (len(plan.Oversized) != 1 || plan.Oversized[0].Key != "fixed-overhead") {
			t.Fatal("fixed overhead did not retain its soft budget boundary")
		}
	}
}

func TestAutomaticPlanBalancesCloudAndOrdinaryUnitsTogether(t *testing.T) {
	recipe := testRecipe()
	recipe.MinecraftSlots = 1
	var cases []Case
	input := timedInput()
	input.Profile = "qualification"
	input.Costs.Cases = map[string]float64{}
	for _, id := range []string{"case.normal-a", "case.normal-b", "case.cloud-a", "case.cloud-b"} {
		test := testCase(id, recipe, Fresh)
		test.Tags = []string{"regression"}
		seconds := 180.0
		if id == "case.cloud-a" || id == "case.cloud-b" {
			test.Capability = "huawei"
			test.Tags = []string{"external"}
			seconds = 120
		}
		cases = append(cases, test)
		input.Costs.Cases[id] = seconds
	}
	plan, err := BuildRunPlan(cases, input)
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Shards) != 2 || len(plan.Catalog) != 4 {
		t.Fatal("provider partitioning prevented a globally balanced two-shard plan")
	}
	for _, shard := range plan.Shards {
		if shard.EstimatedSeconds != 300 || len(shard.Cases) != 2 || !slices.Equal(shard.Providers, []string{"huawei"}) {
			t.Fatal("Minecraft work did not pair ordinary and cloud units within the budget")
		}
	}
}

func TestAutomaticPlanKeepsMixedFreshAndReusableGroupsAtOneShard(t *testing.T) {
	recipe := testRecipe()
	a, b := testCase("case.normal-a", recipe, ObserveReuse), testCase("case.normal-b", recipe, CleanReuse)
	c, d := testCase("case.cloud-a", recipe, Fresh), testCase("case.cloud-b", recipe, Fresh)
	a.Tags, b.Tags = []string{"regression"}, []string{"regression"}
	c.Capability, d.Capability = "huawei", "huawei"
	c.Tags, d.Tags = []string{"external"}, []string{"external"}
	cases := []Case{a, b, c, d}
	input := timedInput()
	input.Profile = "qualification"
	input.MaxShards = 1
	plan, err := BuildRunPlan(cases, input)
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Shards) != 1 || len(plan.Shards[0].Cases) != 4 || !slices.Equal(plan.Shards[0].Providers, []string{"huawei"}) {
		t.Fatal("one shard lost mixed units or duplicated the shared provider dependency")
	}
	execution, err := plan.Execution(cases, 1, "qualification")
	if err != nil {
		t.Fatal(err)
	}
	if len(execution.Groups) != 3 || len(execution.Order) != 4 {
		t.Fatal("Fresh or reusable atomic boundaries changed when providers mixed")
	}
	for _, group := range execution.Groups {
		if group.Key == "recipe:base" && (len(group.Cases) != 2 || group.Cases[0].Capability != "" || group.Cases[1].Capability != "") {
			t.Fatal("reusable group was divided or absorbed a Fresh case")
		}
	}
}

func TestImmutableQualificationRejectsChangedProviderUnion(t *testing.T) {
	ordinary, cloud := timedCase("case.normal", Fresh), timedCase("case.cloud", Fresh)
	cloud.Recipe = ordinary.Recipe
	cloud.Capability, cloud.Tags = "huawei", []string{"external"}
	cases := []Case{ordinary, cloud}
	input := timedInput()
	input.Profile = "qualification"
	for _, providers := range [][]string{{}, {"huawei", "huawei"}, {"dnspod", "huawei"}} {
		plan, err := BuildRunPlan(cases, input)
		if err != nil {
			t.Fatal(err)
		}
		plan.Shards[0].Providers = providers
		if plan.Validate(cases, "qualification") == nil {
			t.Fatal("provider metadata changed without invalidating immutable digest")
		}
		plan.Digest, err = plan.identity()
		if err != nil {
			t.Fatal(err)
		}
		if plan.Validate(cases, "qualification") == nil {
			t.Fatal("rehashed provider metadata differs from current case dependencies")
		}
	}
}
