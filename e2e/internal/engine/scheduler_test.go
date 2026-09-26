package engine

import (
	"context"
	"errors"
	"testing"
	"testing/synctest"
	"time"

	"mc-admin/e2e/internal/environment"
)

func TestResourceAdmissionBypassesBlockedGroupsAndRetainsCleanupCapacity(t *testing.T) {
	for _, noReuse := range []bool{false, true} {
		t.Run(map[bool]string{false: "reuse", true: "no-reuse"}[noReuse], func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				minecraft, ordinary := testRecipe(), testRecipe()
				minecraft.ID, minecraft.MinecraftSlots = "game", 1
				firstStarted, firstFinish := make(chan struct{}), make(chan struct{})
				cleanupStarted, cleanupFinish := make(chan struct{}), make(chan struct{})
				ordinaryRan, secondRan := make(chan struct{}), make(chan struct{})
				first := testCase("case.first", minecraft, ObserveReuse)
				first.Timeout = time.Minute
				first.Run = func(_ context.Context, scope *Scope) error {
					scope.Env.Defer(func(context.Context) error {
						close(cleanupStarted)
						<-cleanupFinish
						return nil
					})
					close(firstStarted)
					<-firstFinish
					return nil
				}
				second := testCase("case.second", minecraft, Fresh)
				second.Run = func(context.Context, *Scope) error { close(secondRan); return nil }
				normal := testCase("case.normal", ordinary, Fresh)
				normal.Run = func(context.Context, *Scope) error { close(ordinaryRan); return nil }
				plan := Plan{Groups: []Group{{Cases: []Case{first}}, {Cases: []Case{second}}, {Cases: []Case{normal}}}}
				options := runnerOptions(t)
				options.MinecraftSlots, options.NoReuse = 1, noReuse
				options.CleanupTimeout = time.Minute
				factory := &fakeFactory{}
				done := make(chan []Result, 1)
				go func() { done <- Run(context.Background(), plan, factory, options) }()
				<-firstStarted
				synctest.Wait()
				select {
				case <-ordinaryRan:
				default:
					t.Fatal("ordinary work stayed behind a blocked Minecraft group")
				}
				select {
				case <-secondRan:
					t.Fatal("Minecraft capacity exceeded")
				default:
				}
				time.Sleep(2 * time.Second)
				close(firstFinish)
				<-cleanupStarted
				synctest.Wait()
				select {
				case <-secondRan:
					t.Fatal("Minecraft capacity released before teardown")
				default:
				}
				close(cleanupFinish)
				results := <-done
				if len(results) != 3 || factory.live != 0 || factory.maxLive > 2 {
					t.Fatalf("resource lifetime failed: results=%+v factory=%+v", results, factory)
				}
				for _, result := range results {
					if result.Status != "passed" {
						t.Fatalf("unexpected failure: %+v", result)
					}
					if result.ID == "case.second" && (result.Timings.SchedulerResourceWaitSeconds < 2 || result.Timings.SchedulerQueueSeconds < result.Timings.SchedulerResourceWaitSeconds) {
						t.Fatalf("resource queue time missing: %+v", result)
					}
				}
			})
		})
	}
}

func TestCancellationRecordsQueuedCasesAndReleasesEnvironments(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		recipe := testRecipe()
		recipe.MinecraftSlots = 1
		started := make(chan struct{})
		first := testCase("case.first", recipe, Fresh)
		cleaned := false
		first.Run = func(ctx context.Context, scope *Scope) error {
			scope.Cleanup(func(ctx context.Context) error { cleaned = ctx.Err() == nil; return nil })
			close(started)
			<-ctx.Done()
			return ctx.Err()
		}
		second := testCase("case.second", recipe, Fresh)
		second.Run = func(context.Context, *Scope) error { t.Error("cancelled queued case executed"); return nil }
		plan := Plan{Groups: []Group{{Cases: []Case{first}}, {Cases: []Case{second}}}}
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		factory := &fakeFactory{}
		options := runnerOptions(t)
		options.MinecraftSlots = 1
		done := make(chan []Result, 1)
		go func() { done <- Run(ctx, plan, factory, options) }()
		<-started
		cancel()
		results := <-done
		if len(results) != 2 || !cleaned || factory.created != 1 || factory.closed != 1 {
			t.Fatalf("cancelled queue lost coverage or cleanup: %+v, factory=%+v", results, factory)
		}
		for _, result := range results {
			if result.Status != "failed" {
				t.Fatalf("cancellation hidden: %+v", result)
			}
		}
	})
}

func TestOversizedGroupFailsWithoutAllocatingOrBlockingOtherCases(t *testing.T) {
	oversized, ordinary := testRecipe(), testRecipe()
	oversized.ID, oversized.MinecraftSlots = "large", 2
	plan := Plan{Groups: []Group{{Cases: []Case{testCase("case.large", oversized, Fresh)}}, {Cases: []Case{testCase("case.normal", ordinary, Fresh)}}}}
	factory := &fakeFactory{}
	options := runnerOptions(t)
	options.MinecraftSlots = 1
	results := Run(context.Background(), plan, factory, options)
	if len(results) != 2 || results[0].Status != "failed" || results[0].Issues[0].Phase != "reservation" || results[1].Status != "passed" || factory.created != 1 || factory.closed != 1 {
		t.Fatalf("oversized group blocked ordinary execution: %+v", results)
	}
}

func TestLifecycleTimingsIncludeReusableGroupRetirement(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		recipe := testRecipe()
		recipe.Providers[0].Setup = func(_ context.Context, env *environment.Environment) error {
			time.Sleep(100 * time.Millisecond)
			env.Defer(func(context.Context) error { time.Sleep(30 * time.Millisecond); return nil })
			return nil
		}
		recipe.Providers[0].Verify = func(context.Context, *environment.Environment) error { time.Sleep(25 * time.Millisecond); return nil }
		first, second := testCase("case.first", recipe, CleanReuse), testCase("case.second", recipe, CleanReuse)
		action := func(_ context.Context, scope *Scope) error {
			time.Sleep(100 * time.Millisecond)
			scope.Cleanup(func(context.Context) error { time.Sleep(50 * time.Millisecond); return nil })
			return nil
		}
		first.Run, second.Run = action, action
		factory := &phaseFactory{
			reserve: func(context.Context) (func(), error) { time.Sleep(10 * time.Millisecond); return func() {}, nil },
			capture: func(context.Context, *environment.Environment) error { time.Sleep(20 * time.Millisecond); return nil },
		}
		results := runGroup(context.Background(), Group{Cases: []Case{first, second}}, factory, runnerOptions(t))
		if results[0].Seconds != .285 || results[1].Seconds != .225 || results[0].Timings.SetupSeconds != .1 || results[1].Timings.SetupSeconds != 0 || results[1].Timings.TeardownSeconds != .03 || results[1].Timings.DiagnosticsSeconds != .02 || !results[1].Reused {
			t.Fatalf("lifecycle timings do not include complete retirement: %+v", results)
		}
		for _, result := range results {
			timing := result.Timings
			sum := timing.ReservationSeconds + timing.SetupSeconds + timing.AssertionSeconds + timing.CaseCleanupSeconds + timing.VerificationSeconds + timing.DiagnosticsSeconds + timing.TeardownSeconds
			if delta := result.Seconds - sum; delta < -1e-9 || delta > 1e-9 {
				t.Fatalf("phase accounting differs from execution: %+v", result)
			}
		}
	})
}

func TestFailedGroupReleasesAdmissionForNextGroup(t *testing.T) {
	for _, mode := range []string{"setup", "assertion", "cleanup", "diagnostics"} {
		t.Run(mode, func(t *testing.T) {
			recipe := testRecipe()
			recipe.MinecraftSlots = 1
			first, second := testCase("case.first", recipe, Fresh), testCase("case.second", recipe, Fresh)
			first.Run = func(_ context.Context, scope *Scope) error {
				if mode == "cleanup" {
					scope.Cleanup(func(context.Context) error { return errors.New("cleanup failure") })
				}
				if mode == "assertion" {
					return errors.New("assertion failure")
				}
				return nil
			}
			factory := &phaseFactory{fakeFactory: fakeFactory{setupFailure: mode == "setup"}, reserve: func(context.Context) (func(), error) { return func() {}, nil }}
			factory.capture = func(_ context.Context, env *environment.Environment) error {
				if mode == "diagnostics" && env.ID == "1" {
					return errors.New("capture failure")
				}
				return nil
			}
			options := runnerOptions(t)
			options.MinecraftSlots = 1
			results := Run(context.Background(), Plan{Groups: []Group{{Cases: []Case{first}}, {Cases: []Case{second}}}}, factory, options)
			if len(results) != 2 || results[0].Status != "failed" || results[1].Status != "passed" || factory.created != 2 || factory.closed != 2 || factory.live != 0 {
				t.Fatalf("failed group retained admission: %+v, factory=%+v", results, factory)
			}
		})
	}
}
