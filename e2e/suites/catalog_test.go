package suites

import (
	"regexp"
	"slices"
	"testing"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func TestRegressionCatalogIncludesAllCasesExceptDNSPod(t *testing.T) {
	catalog := Catalog(fixtures.NewFactory(fixtures.Options{}, nil, nil).Recipes())
	wanted := map[string]bool{}
	for _, test := range catalog {
		if test.Capability == "dnspod" {
			if slices.Contains(test.Tags, "regression") {
				t.Fatalf("DNSPod case %s entered default regression", test.ID)
			}
			continue
		}
		if !slices.Contains(test.Tags, "regression") {
			t.Fatalf("current case %s lacks regression tag", test.ID)
		}
		wanted[test.ID] = true
	}
	plan, err := engine.BuildPlan(catalog, engine.Selection{Tag: "regression", ShardIndex: 1, ShardCount: 1})
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Order) != len(wanted) {
		t.Fatalf("regression selection has %d cases, expected %d", len(plan.Order), len(wanted))
	}
	for _, id := range plan.Order {
		if !wanted[id] {
			t.Fatalf("regression selected unexpected or duplicate case %s", id)
		}
		delete(wanted, id)
	}
	for _, test := range catalog {
		if test.Capability == "dnspod" {
			continue
		}
		filtered, err := engine.BuildPlan(catalog, engine.Selection{Tag: "regression", Suite: test.Suite, Match: "^" + regexp.QuoteMeta(test.ID) + "$", ShardIndex: 1, ShardCount: 1})
		if err != nil {
			t.Fatal(err)
		}
		if !slices.Equal(filtered.Order, []string{test.ID}) {
			t.Fatalf("explicit suite/case selection changed for %s: %v", test.ID, filtered.Order)
		}
	}
}
