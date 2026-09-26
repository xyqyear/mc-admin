package engine

import (
	"context"
	"fmt"
	"path/filepath"
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
	Workers             int
	MinecraftSlots      int
	NoReuse             bool
	SetupTimeout        time.Duration
	CleanupTimeout      time.Duration
	Directory           string
	Redactor            *evidence.Redactor
	Progress            func(string)
	queueSeconds        float64
	resourceWaitSeconds float64
	abort               context.CancelCauseFunc
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
	Timings     Timings   `json:"timings"`
	Steps       []Step    `json:"steps"`
	Issues      []Issue   `json:"issues,omitempty"`
}

type Timings struct {
	SchedulerQueueSeconds        float64 `json:"scheduler_queue_seconds"`
	SchedulerResourceWaitSeconds float64 `json:"scheduler_resource_wait_seconds"`
	ReservationSeconds           float64 `json:"reservation_seconds"`
	SetupSeconds                 float64 `json:"setup_seconds"`
	AssertionSeconds             float64 `json:"assertion_seconds"`
	CaseCleanupSeconds           float64 `json:"case_cleanup_seconds"`
	VerificationSeconds          float64 `json:"verification_seconds"`
	DiagnosticsSeconds           float64 `json:"diagnostics_seconds"`
	TeardownSeconds              float64 `json:"teardown_seconds"`
}

func (r *Result) issue(phase string, err error, redactor *evidence.Redactor) {
	if err != nil {
		r.Status = "failed"
		r.Issues = append(r.Issues, Issue{phase, redactor.Text(err.Error())})
	}
}

func runGroup(ctx context.Context, group Group, factory Factory, options Options) []Result {
	ctx, cancel := context.WithCancelCause(ctx)
	defer cancel(nil)
	var env *environment.Environment
	var release func()
	var results []Result
	closeEnv := func(result *Result) {
		if env != nil {
			result.issue("diagnostics", timedPhase(&result.Timings.DiagnosticsSeconds, context.Background(), options.CleanupTimeout, func(ctx context.Context) error {
				return factory.Capture(ctx, env)
			}), options.Redactor)
			err := timedPhase(&result.Timings.TeardownSeconds, context.Background(), options.CleanupTimeout, env.Close)
			result.issue("teardown", err, options.Redactor)
			if err != nil {
				cause := fmt.Errorf("environment %s teardown failed; resource ownership is unresolved: %w", env.ID, err)
				cancel(cause)
				if options.abort != nil {
					options.abort(cause)
				}
				// Failed teardown cannot establish that the reserved resources are free.
				release = nil
			}
			env = nil
		}
		if release != nil {
			release()
			release = nil
		}
	}
	for index, test := range group.Cases {
		result := Result{ID: test.ID, Suite: test.Suite, Started: time.Now().UTC(), Status: "passed"}
		if index == 0 {
			result.Timings.SchedulerQueueSeconds = options.queueSeconds
			result.Timings.SchedulerResourceWaitSeconds = options.resourceWaitSeconds
		}
		if options.Progress != nil {
			options.Progress("RUN " + test.ID)
		}
		recorder, err := evidence.Open(filepath.Join(options.Directory, "cases", test.ID+".jsonl"), options.Redactor)
		if err != nil {
			result.issue("report", err, options.Redactor)
			closeEnv(&result)
			result.Seconds = time.Since(result.Started).Seconds()
			results = append(results, result)
			continue
		}
		scope := &Scope{Recorder: recorder}
		if ctx.Err() != nil {
			result.issue("cancelled", context.Cause(ctx), options.Redactor)
		} else {
			result.Reused = env != nil
			if env == nil {
				reservationStarted := time.Now()
				err = environment.Protect(func() error {
					var err error
					release, err = factory.Reserve(ctx, test.Recipe)
					return err
				})
				result.Timings.ReservationSeconds = time.Since(reservationStarted).Seconds()
				if err == nil {
					err = context.Cause(ctx)
				}
				result.issue("reservation", err, options.Redactor)
				if err == nil {
					err = timedPhase(&result.Timings.SetupSeconds, ctx, options.SetupTimeout, func(setupCtx context.Context) error {
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
				err = timedPhase(&result.Timings.AssertionSeconds, ctx, test.Timeout, func(testCtx context.Context) error { return test.Run(testCtx, scope) })
				result.issue("assertion", err, options.Redactor)
			}
		}
		result.issue("case_cleanup", timedPhase(&result.Timings.CaseCleanupSeconds, context.Background(), options.CleanupTimeout, func(ctx context.Context) error {
			return environment.CleanupAll(ctx, scope.cleanups)
		}), options.Redactor)
		if result.Status == "passed" && test.Isolation != Fresh && !options.NoReuse {
			result.issue("verification", timedPhase(&result.Timings.VerificationSeconds, context.Background(), options.CleanupTimeout, env.Verify), options.Redactor)
		}
		if result.Status != "passed" || test.Isolation == Fresh || options.NoReuse || index == len(group.Cases)-1 {
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
	return results
}

func timedPhase(seconds *float64, parent context.Context, budget time.Duration, action func(context.Context) error) error {
	started := time.Now()
	defer func() { *seconds += time.Since(started).Seconds() }()
	return runPhase(parent, budget, action)
}

func runPhase(parent context.Context, budget time.Duration, action func(context.Context) error) error {
	ctx, cancel := context.WithTimeout(parent, budget)
	defer cancel()
	if err := environment.Protect(func() error { return action(ctx) }); err != nil {
		return err
	}
	return ctx.Err()
}
