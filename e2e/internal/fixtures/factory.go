package fixtures

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/evidence"
	"mc-admin/e2e/internal/platform"
)

const DefaultMinecraftImage = "itzg/minecraft-server:java25@sha256:59feb0a1ef286f20a20560c56adf5b927155bfa842951f5db8b8bbc5a1a3ebde"
const DefaultMinecraftVersion = "1.21.11"

type Options struct {
	Image            string
	MinecraftImage   string
	MinecraftVersion string
	PortDirectory    string
	MinecraftSlots   int
	ExternalConfig   string
}

type Factory struct {
	Options  Options
	Journal  *platform.Journal
	Redactor *evidence.Redactor
	slots    chan struct{}
	slotGate chan struct{}
}

func NewFactory(options Options, journal *platform.Journal, redactor *evidence.Redactor) *Factory {
	return &Factory{Options: options, Journal: journal, Redactor: redactor, slots: make(chan struct{}, options.MinecraftSlots), slotGate: make(chan struct{}, 1)}
}

type Recipes struct{ Base, Server, Lifecycle, Running, Backup, World *environment.Recipe }

func (f *Factory) Recipes() Recipes {
	backend := environment.Provider{ID: "backend", Setup: f.backend, Verify: verifyBackend}
	ports := environment.Provider{ID: "ports", Setup: f.ports, Verify: func(context.Context, *environment.Environment) error { return nil }}
	server := environment.Provider{ID: "server", DependsOn: []string{"backend", "ports"}, Setup: f.server, Verify: verifyServer}
	running := environment.Provider{ID: "running", DependsOn: []string{"server"}, Setup: f.running, Verify: verifyRunning}
	restic := environment.Provider{ID: "restic", DependsOn: []string{"backend"}, Setup: f.restic}
	return Recipes{
		Base:      &environment.Recipe{ID: "backend-v1", Providers: []environment.Provider{backend}},
		Server:    &environment.Recipe{ID: "server-v1", Providers: []environment.Provider{backend, ports, server}},
		Lifecycle: &environment.Recipe{ID: "lifecycle-v1", Providers: []environment.Provider{backend, ports, server}, MinecraftSlots: 1},
		Running:   &environment.Recipe{ID: "running-v1", Providers: []environment.Provider{backend, ports, server, running}, MinecraftSlots: 1},
		Backup:    &environment.Recipe{ID: "backup-v1", Providers: []environment.Provider{backend, ports, server, restic}},
		World:     &environment.Recipe{ID: "world-v1", Providers: []environment.Provider{backend, ports, server, running, restic}, MinecraftSlots: 1},
	}
}

func (f *Factory) acquireSlots(ctx context.Context, count int) (func(), error) {
	if count < 0 || count > cap(f.slots) {
		return nil, fmt.Errorf("requested %d Minecraft slots with budget %d", count, cap(f.slots))
	}
	if count == 0 {
		return func() {}, nil
	}
	// Serialize weighted acquisition so competing recipes cannot each hold a partial reservation.
	select {
	case f.slotGate <- struct{}{}:
		defer func() { <-f.slotGate }()
	case <-ctx.Done():
		return nil, ctx.Err()
	}
	acquired := 0
	release := func() {
		for range acquired {
			<-f.slots
		}
	}
	for range count {
		select {
		case f.slots <- struct{}{}:
			acquired++
		case <-ctx.Done():
			release()
			return nil, ctx.Err()
		}
	}
	return release, nil
}

func (f *Factory) Reserve(ctx context.Context, recipe *environment.Recipe) (func(), error) {
	return f.acquireSlots(ctx, recipe.MinecraftSlots)
}

func (f *Factory) New(ctx context.Context, recipe *environment.Recipe) (env *environment.Environment, err error) {
	id := platform.ID()
	dir := filepath.Join(f.Journal.Manifest.Directory, "runtime", id)
	env = environment.New(id, dir, nil)
	if err = f.Journal.AddEnvironment(id); err != nil {
		return env, err
	}
	defer func() { env.Defer(func(ctx context.Context) error { return f.Journal.CleanupEnvironment(ctx, id) }) }()
	if err = os.Mkdir(dir, 0700); err != nil {
		return env, err
	}
	artifactDir := filepath.Join(f.Journal.Manifest.Directory, "environments", id)
	if err = os.MkdirAll(artifactDir, 0700); err != nil {
		return env, err
	}
	recorder, err := evidence.Open(filepath.Join(artifactDir, "trace.jsonl"), f.Redactor)
	if err != nil {
		return env, err
	}
	env.Recorder = recorder
	env.Defer(func(context.Context) error { return recorder.Close() })
	env.Set("options", f.Options)
	env.Set("recipe", recipe)
	env.Set("journal", f.Journal)
	if err = evidence.WriteJSON(filepath.Join(artifactDir, "recipe.json"), map[string]any{"id": recipe.ID, "minecraft_slots": recipe.MinecraftSlots}); err != nil {
		return env, err
	}
	err = environment.Protect(func() error { return env.Setup(ctx, recipe) })
	return env, err
}

func (f *Factory) Capture(ctx context.Context, env *environment.Environment) error {
	return f.Journal.Capture(ctx, env.ID, f.Redactor)
}

func (f *Factory) ports(ctx context.Context, env *environment.Environment) error {
	lease, err := platform.LeasePorts(ctx, f.Journal.Docker, f.Options.PortDirectory, 2)
	if err != nil {
		return err
	}
	env.Set("ports", lease.Ports)
	env.Set("port-lease", lease)
	env.Defer(func(context.Context) error { return lease.Close() })
	return nil
}
