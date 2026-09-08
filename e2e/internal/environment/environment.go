package environment

import (
	"context"
	"errors"
	"fmt"
	"sort"

	"mc-admin/e2e/internal/evidence"
)

type Cleanup func(context.Context) error

type Provider struct {
	ID        string
	DependsOn []string
	Setup     func(context.Context, *Environment) error
	Verify    func(context.Context, *Environment) error
}

type Recipe struct {
	ID             string
	Providers      []Provider
	MinecraftSlots int
}

func (r *Recipe) Ordered() ([]Provider, error) {
	if r == nil || r.ID == "" {
		return nil, fmt.Errorf("recipe needs an ID")
	}
	providers := map[string]Provider{}
	for _, p := range r.Providers {
		if p.ID == "" || p.Setup == nil {
			return nil, fmt.Errorf("recipe %s has an invalid provider", r.ID)
		}
		if _, ok := providers[p.ID]; ok {
			return nil, fmt.Errorf("duplicate provider %s", p.ID)
		}
		providers[p.ID] = p
	}
	state := map[string]int{}
	var order []Provider
	var visit func(string) error
	visit = func(id string) error {
		p, ok := providers[id]
		if !ok {
			return fmt.Errorf("missing provider %s", id)
		}
		if state[id] == 1 {
			return fmt.Errorf("provider cycle at %s", id)
		}
		if state[id] == 2 {
			return nil
		}
		state[id] = 1
		deps := append([]string(nil), p.DependsOn...)
		sort.Strings(deps)
		for _, dep := range deps {
			if err := visit(dep); err != nil {
				return err
			}
		}
		state[id] = 2
		order = append(order, p)
		return nil
	}
	ids := make([]string, 0, len(providers))
	for id := range providers {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		if err := visit(id); err != nil {
			return nil, err
		}
	}
	if len(order) == 0 || r.MinecraftSlots < 0 {
		return nil, fmt.Errorf("invalid recipe %s", r.ID)
	}
	return order, nil
}

type Environment struct {
	ID        string
	Dir       string
	Recorder  *evidence.Recorder
	values    map[string]any
	cleanups  []Cleanup
	providers []Provider
}

func New(id, dir string, recorder *evidence.Recorder) *Environment {
	return &Environment{ID: id, Dir: dir, Recorder: recorder, values: map[string]any{}}
}

func (e *Environment) Set(key string, value any) { e.values[key] = value }
func Get[T any](e *Environment, key string) T {
	value, ok := e.values[key].(T)
	if !ok {
		panic(fmt.Sprintf("environment %s has no resource %q of expected type", e.ID, key))
	}
	return value
}
func (e *Environment) Defer(cleanup Cleanup) { e.cleanups = append(e.cleanups, cleanup) }

func (e *Environment) Setup(ctx context.Context, recipe *Recipe) error {
	providers, err := recipe.Ordered()
	if err != nil {
		return err
	}
	for _, p := range providers {
		e.Recorder.Event("provider_setup", map[string]string{"provider": p.ID, "environment": e.ID})
		if err := p.Setup(ctx, e); err != nil {
			return fmt.Errorf("provider %s: %w", p.ID, err)
		}
		e.providers = append(e.providers, p)
	}
	return nil
}

func (e *Environment) Verify(ctx context.Context) error {
	for _, p := range e.providers {
		if p.Verify == nil {
			return fmt.Errorf("provider %s does not support verified reuse", p.ID)
		}
		if err := p.Verify(ctx, e); err != nil {
			return fmt.Errorf("provider %s invariant: %w", p.ID, err)
		}
	}
	return nil
}

func Protect(action func() error) (err error) {
	defer func() {
		if value := recover(); value != nil {
			err = fmt.Errorf("panic: %v", value)
		}
	}()
	return action()
}

func CleanupAll(ctx context.Context, cleanups []Cleanup) error {
	var errs []error
	for i := len(cleanups) - 1; i >= 0; i-- {
		if err := Protect(func() error { return cleanups[i](ctx) }); err != nil {
			errs = append(errs, err)
		}
	}
	return errors.Join(errs...)
}

func (e *Environment) Close(ctx context.Context) error {
	err := CleanupAll(ctx, e.cleanups)
	e.cleanups = nil
	return err
}
