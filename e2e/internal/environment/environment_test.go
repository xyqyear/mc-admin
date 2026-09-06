package environment

import (
	"context"
	"errors"
	"reflect"
	"testing"
)

func TestProviderGraphAndPartialSetupCleanup(t *testing.T) {
	var actions []string
	setup := func(name string, fail bool) func(context.Context, *Environment) error {
		return func(_ context.Context, e *Environment) error {
			actions = append(actions, "setup:"+name)
			e.Defer(func(context.Context) error { actions = append(actions, "cleanup:"+name); return nil })
			if fail {
				return errors.New("partial allocation")
			}
			return nil
		}
	}
	recipe := &Recipe{ID: "graph", Providers: []Provider{
		{ID: "game", DependsOn: []string{"backend"}, Setup: setup("game", true)},
		{ID: "backend", DependsOn: []string{"database"}, Setup: setup("backend", false)},
		{ID: "database", Setup: setup("database", false)},
	}}
	e := New("test", "", nil)
	if err := e.Setup(context.Background(), recipe); err == nil {
		t.Fatal("expected setup failure")
	}
	if err := e.Close(context.Background()); err != nil {
		t.Fatal(err)
	}
	want := []string{"setup:database", "setup:backend", "setup:game", "cleanup:game", "cleanup:backend", "cleanup:database"}
	if !reflect.DeepEqual(actions, want) {
		t.Fatalf("actions=%v", actions)
	}
	if err := e.Close(context.Background()); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(actions, want) {
		t.Fatal("cleanup ran twice")
	}
}

func TestRejectInvalidProviderGraphs(t *testing.T) {
	setup := func(context.Context, *Environment) error { return nil }
	for name, providers := range map[string][]Provider{
		"missing":   {{ID: "a", DependsOn: []string{"missing"}, Setup: setup}},
		"cycle":     {{ID: "a", DependsOn: []string{"b"}, Setup: setup}, {ID: "b", DependsOn: []string{"a"}, Setup: setup}},
		"duplicate": {{ID: "a", Setup: setup}, {ID: "a", Setup: setup}},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := (&Recipe{ID: name, Providers: providers}).Ordered(); err == nil {
				t.Fatal("invalid graph accepted")
			}
		})
	}
}

func TestCleanupContinuesAfterErrorAndPanic(t *testing.T) {
	called := false
	err := CleanupAll(context.Background(), []Cleanup{
		func(context.Context) error { called = true; return nil },
		func(context.Context) error { return errors.New("failure") },
		func(context.Context) error { panic("panic") },
	})
	if err == nil || !called {
		t.Fatalf("cleanup failed to continue: %v, called=%t", err, called)
	}
}
