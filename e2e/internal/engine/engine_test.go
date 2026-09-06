package engine

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"sync"
	"testing"
	"time"

	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/evidence"
)

func testRecipe() *environment.Recipe {
	return &environment.Recipe{ID: "base", Providers: []environment.Provider{{ID: "base", Setup: func(context.Context, *environment.Environment) error { return nil }, Verify: func(context.Context, *environment.Environment) error { return nil }}}}
}

func testCase(id string, recipe *environment.Recipe, isolation Isolation) Case {
	return Case{ID: id, Suite: "test", Tags: []string{"smoke"}, Recipe: recipe, Isolation: isolation, Timeout: time.Second, Run: func(context.Context, *Scope) error { return nil }}
}

func TestShardPartitionIsCompleteAndStable(t *testing.T) {
	recipe := testRecipe()
	var catalog []Case
	for i := range 30 {
		isolation := Fresh
		if i%3 == 0 {
			isolation = ObserveReuse
		}
		catalog = append(catalog, testCase(fmt.Sprintf("case.%02d", i), recipe, isolation))
	}
	seen := map[string]int{}
	for shard := 1; shard <= 4; shard++ {
		selection := Selection{ShardIndex: shard, ShardCount: 4, Seed: 73}
		first, err := BuildPlan(catalog, selection)
		if err != nil {
			t.Fatal(err)
		}
		second, err := BuildPlan(catalog, selection)
		if err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(first.Order, second.Order) {
			t.Fatal("seeded order changed")
		}
		for _, id := range first.Order {
			seen[id]++
		}
	}
	if len(seen) != len(catalog) {
		t.Fatalf("partition lost cases: %d/%d", len(seen), len(catalog))
	}
	for id, count := range seen {
		if count != 1 {
			t.Fatalf("%s occurs %d times", id, count)
		}
	}
}

func TestCatalogRejectsAmbiguousOrUnsafeDeclarations(t *testing.T) {
	recipe := testRecipe()
	base := testCase("case.one", recipe, Fresh)
	for name, catalog := range map[string][]Case{
		"duplicate":                    {base, base},
		"different recipe definitions": {base, testCase("case.two", testRecipe(), Fresh)},
		"implicit isolation":           {testCase("case.two", recipe, "")},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := BuildPlan(catalog, Selection{ShardIndex: 1, ShardCount: 1}); err == nil {
				t.Fatal("invalid catalog accepted")
			}
		})
	}
	recipe.Providers[0].Verify = nil
	if _, err := BuildPlan([]Case{testCase("case.reuse", recipe, ObserveReuse)}, Selection{ShardIndex: 1, ShardCount: 1}); err == nil {
		t.Fatal("unverifiable reuse accepted")
	}
}

type fakeFactory struct {
	mu                             sync.Mutex
	created, closed, live, maxLive int
	setupFailure                   bool
}

func (f *fakeFactory) New(ctx context.Context, recipe *environment.Recipe) (*environment.Environment, error) {
	f.mu.Lock()
	f.created++
	number := f.created
	f.live++
	if f.live > f.maxLive {
		f.maxLive = f.live
	}
	f.mu.Unlock()
	env := environment.New(fmt.Sprint(number), "", nil)
	env.Defer(func(context.Context) error { f.mu.Lock(); defer f.mu.Unlock(); f.closed++; f.live--; return nil })
	if f.setupFailure && number == 1 {
		return env, errors.New("setup failed after allocation")
	}
	return env, env.Setup(ctx, recipe)
}
func (f *fakeFactory) Capture(context.Context, *environment.Environment) error { return nil }

func runnerOptions(t *testing.T) Options {
	t.Helper()
	dir := t.TempDir()
	if err := os.Mkdir(filepath.Join(dir, "cases"), 0700); err != nil {
		t.Fatal(err)
	}
	return Options{Workers: 2, SetupTimeout: time.Second, CleanupTimeout: time.Second, Directory: dir, Redactor: &evidence.Redactor{}}
}

func TestReuseFailureRetirementAndFreshExecution(t *testing.T) {
	for _, mode := range []string{"reuse", "fresh", "no-reuse", "assertion", "panic", "cleanup", "verification", "setup"} {
		t.Run(mode, func(t *testing.T) {
			recipe := testRecipe()
			first := testCase("case.first", recipe, CleanReuse)
			second := testCase("case.second", recipe, ObserveReuse)
			switch mode {
			case "fresh":
				first.Isolation = Fresh
				second.Isolation = Fresh
			case "assertion":
				first.Run = func(context.Context, *Scope) error { return errors.New("business failure") }
			case "panic":
				first.Run = func(context.Context, *Scope) error { panic("business panic") }
			case "cleanup":
				first.Run = func(_ context.Context, s *Scope) error {
					s.Cleanup(func(context.Context) error { return errors.New("cleanup failure") })
					return nil
				}
			case "verification":
				recipe.Providers[0].Verify = func(_ context.Context, e *environment.Environment) error {
					if e.ID == "1" {
						return errors.New("dirty baseline")
					}
					return nil
				}
			}
			plan, err := BuildPlan([]Case{first, second}, Selection{ShardIndex: 1, ShardCount: 1})
			if err != nil {
				t.Fatal(err)
			}
			factory := &fakeFactory{setupFailure: mode == "setup"}
			options := runnerOptions(t)
			options.NoReuse = mode == "no-reuse"
			results := Run(context.Background(), plan, factory, options)
			want := 2
			if mode == "reuse" {
				want = 1
			}
			if factory.created != want || factory.closed != want || factory.live != 0 {
				t.Fatalf("created=%d closed=%d live=%d, want %d", factory.created, factory.closed, factory.live, want)
			}
			if len(results) != 2 || results[1].Status != "passed" {
				t.Fatalf("subsequent independent case did not pass: %+v", results)
			}
			if mode == "assertion" || mode == "panic" || mode == "cleanup" || mode == "verification" || mode == "setup" {
				if results[0].Status != "failed" {
					t.Fatal("failure was hidden")
				}
			}
			if mode == "reuse" && (!results[1].Reused || results[0].Environment != results[1].Environment) {
				t.Fatal("compatible environment was not reused")
			}
		})
	}
}

func TestCancellationUsesIndependentCleanupDeadline(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	recipe := testRecipe()
	test := testCase("case.cancel", recipe, Fresh)
	cleaned := false
	test.Run = func(_ context.Context, s *Scope) error {
		s.Cleanup(func(ctx context.Context) error { cleaned = ctx.Err() == nil; return nil })
		cancel()
		return ctx.Err()
	}
	plan, err := BuildPlan([]Case{test}, Selection{ShardIndex: 1, ShardCount: 1})
	if err != nil {
		t.Fatal(err)
	}
	factory := &fakeFactory{}
	results := Run(ctx, plan, factory, runnerOptions(t))
	if !cleaned || factory.closed != 1 || results[0].Status != "failed" {
		t.Fatalf("cancellation lost cleanup: %+v", results)
	}
}

func TestWorkerBudgetBoundsLiveEnvironments(t *testing.T) {
	recipe := testRecipe()
	var cases []Case
	for i := range 12 {
		test := testCase(fmt.Sprintf("case.%02d", i), recipe, Fresh)
		test.Run = func(context.Context, *Scope) error { time.Sleep(time.Millisecond); return nil }
		cases = append(cases, test)
	}
	plan, err := BuildPlan(cases, Selection{ShardIndex: 1, ShardCount: 1})
	if err != nil {
		t.Fatal(err)
	}
	factory := &fakeFactory{}
	options := runnerOptions(t)
	options.Workers = 3
	results := Run(context.Background(), plan, factory, options)
	if factory.maxLive > 3 || factory.live != 0 || len(results) != 12 {
		t.Fatalf("worker budget violated: %+v", factory)
	}
}
