package engine

import (
	"context"
	"fmt"
	"path/filepath"
	"sort"
	"sync"
	"time"

	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/evidence"
)

type Scope struct {
	Env      *environment.Environment
	Recorder *evidence.Recorder
	cleanups []environment.Cleanup
	steps    []Step
}

type Step struct {
	Name    string  `json:"name"`
	Seconds float64 `json:"seconds"`
	Error   string  `json:"error,omitempty"`
}

func (s *Scope) Cleanup(cleanup environment.Cleanup) { s.cleanups = append(s.cleanups, cleanup) }
func (s *Scope) Step(name string, action func() error) error {
	start := time.Now()
	s.Recorder.Event("step_start", map[string]string{"step": name})
	err := environment.Protect(action)
	step := Step{Name: name, Seconds: time.Since(start).Seconds()}
	if err != nil {
		step.Error = s.Recorder.Redactor.Text(err.Error())
	}
	s.steps = append(s.steps, step)
	s.Recorder.Event("step_end", step)
	if err != nil {
		return fmt.Errorf("%s: %w", name, err)
	}
	return nil
}

type Factory interface {
	Reserve(context.Context, *environment.Recipe) (func(), error)
	New(context.Context, *environment.Recipe) (*environment.Environment, error)
	Capture(context.Context, *environment.Environment) error
}

type Options struct {
	Workers        int
	NoReuse        bool
	SetupTimeout   time.Duration
	CleanupTimeout time.Duration
	Directory      string
	Redactor       *evidence.Redactor
	Progress       func(string)
}

type Issue struct {
	Phase   string `json:"phase"`
	Message string `json:"message"`
}
type Result struct {
	ID          string    `json:"id"`
	Suite       string    `json:"suite"`
	Environment string    `json:"environment,omitempty"`
	Reused      bool      `json:"reused"`
	Status      string    `json:"status"`
	Started     time.Time `json:"started"`
	Seconds     float64   `json:"seconds"`
	Steps       []Step    `json:"steps"`
	Issues      []Issue   `json:"issues,omitempty"`
}

func (r *Result) issue(phase string, err error, redactor *evidence.Redactor) {
	if err != nil {
		r.Status = "failed"
		r.Issues = append(r.Issues, Issue{phase, redactor.Text(err.Error())})
	}
}

func Run(ctx context.Context, plan Plan, factory Factory, options Options) []Result {
	jobs := make(chan Group)
	var mu sync.Mutex
	var results []Result
	var workers sync.WaitGroup
	for range options.Workers {
		workers.Add(1)
		go func() {
			defer workers.Done()
			for group := range jobs {
				groupResults := runGroup(ctx, group, factory, options)
				mu.Lock()
				results = append(results, groupResults...)
				mu.Unlock()
			}
		}()
	}
	for _, group := range plan.Groups {
		jobs <- group
	}
	close(jobs)
	workers.Wait()
	sort.Slice(results, func(i, j int) bool { return results[i].ID < results[j].ID })
	return results
}

func runGroup(ctx context.Context, group Group, factory Factory, options Options) []Result {
	var env *environment.Environment
	var release func()
	var results []Result
	closeEnv := func(result *Result) {
		if env != nil {
			result.issue("diagnostics", runPhase(context.Background(), options.CleanupTimeout, func(ctx context.Context) error {
				return factory.Capture(ctx, env)
			}), options.Redactor)
			result.issue("teardown", runPhase(context.Background(), options.CleanupTimeout, env.Close), options.Redactor)
			env = nil
		}
		if release != nil {
			release()
			release = nil
		}
	}
	for _, test := range group.Cases {
		result := Result{ID: test.ID, Suite: test.Suite, Started: time.Now().UTC(), Status: "passed"}
		if options.Progress != nil {
			options.Progress("RUN " + test.ID)
		}
		recorder, err := evidence.Open(filepath.Join(options.Directory, "cases", test.ID+".jsonl"), options.Redactor)
		if err != nil {
			result.issue("report", err, options.Redactor)
			closeEnv(&result)
			results = append(results, result)
			continue
		}
		scope := &Scope{Recorder: recorder}
		if ctx.Err() != nil {
			result.issue("cancelled", ctx.Err(), options.Redactor)
		} else {
			result.Reused = env != nil
			if env == nil {
				err = environment.Protect(func() error {
					var err error
					release, err = factory.Reserve(ctx, test.Recipe)
					return err
				})
				result.issue("reservation", err, options.Redactor)
				if err == nil {
					err = runPhase(ctx, options.SetupTimeout, func(setupCtx context.Context) error {
						var err error
						env, err = factory.New(setupCtx, test.Recipe)
						return err
					})
					result.issue("setup", err, options.Redactor)
				}
			}
			if env != nil {
				result.Environment = env.ID
				scope.Env = env
			}
			if result.Status == "passed" {
				testCtx, cancel := context.WithTimeout(ctx, test.Timeout)
				err = environment.Protect(func() error { return test.Run(testCtx, scope) })
				if err == nil {
					err = testCtx.Err()
				}
				cancel()
				result.issue("assertion", err, options.Redactor)
			}
		}
		result.issue("case_cleanup", runPhase(context.Background(), options.CleanupTimeout, func(ctx context.Context) error {
			return environment.CleanupAll(ctx, scope.cleanups)
		}), options.Redactor)
		if result.Status == "passed" && test.Isolation != Fresh && !options.NoReuse {
			result.issue("verification", runPhase(context.Background(), options.CleanupTimeout, env.Verify), options.Redactor)
		}
		if result.Status != "passed" || test.Isolation == Fresh || options.NoReuse {
			closeEnv(&result)
		}
		result.Steps = scope.steps
		result.issue("report", recorder.Close(), options.Redactor)
		if result.Status != "passed" {
			closeEnv(&result)
		}
		result.Seconds = time.Since(result.Started).Seconds()
		results = append(results, result)
		if options.Progress != nil {
			options.Progress(fmt.Sprintf("%s %s (%.1fs, environment=%s, reused=%t)", result.Status, test.ID, result.Seconds, result.Environment, result.Reused))
		}
	}
	if len(results) > 0 {
		closeEnv(&results[len(results)-1])
	}
	return results
}

func runPhase(parent context.Context, budget time.Duration, action func(context.Context) error) error {
	ctx, cancel := context.WithTimeout(parent, budget)
	defer cancel()
	if err := environment.Protect(func() error { return action(ctx) }); err != nil {
		return err
	}
	return ctx.Err()
}
