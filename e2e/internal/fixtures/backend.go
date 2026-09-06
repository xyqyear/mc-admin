package fixtures

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/evidence"
	"mc-admin/e2e/internal/platform"
)

type Backend struct {
	Name      string
	URL       string
	Master    string
	Password  string
	Admin     *api.Client
	Configs   map[string]any
	ServerIDs []string
	Docker    platform.Docker
}

func BackendOf(env *environment.Environment) *Backend {
	return environment.Get[*Backend](env, "backend")
}

func (f *Factory) backend(ctx context.Context, env *environment.Environment) error {
	b := &Backend{Name: "mca-e2e-" + env.ID, Master: platform.ID() + platform.ID() + platform.ID(), Password: platform.ID() + platform.ID(), Docker: f.Journal.Docker, Configs: map[string]any{}}
	f.Redactor.Add(b.Master, b.Password)
	env.Set("backend", b)
	for _, name := range []string{"servers", "archives", "logs", "restic"} {
		if err := os.Mkdir(filepath.Join(env.Dir, name), 0755); err != nil {
			return err
		}
	}
	settings := []string{
		"MASTER_TOKEN=" + b.Master, "JWT__SECRET_KEY=" + b.Password,
		"SERVER_PATH=" + filepath.Join(env.Dir, "servers"), "DATABASE_URL=sqlite+aiosqlite:////data/db.sqlite3",
		"LOGS_DIR=/data/logs", "ARCHIVE_PATH=/data/archives", "AUDIT__LOG_FILE=/data/logs/operations.log",
		"MC_ADMIN_CONFIG=/data/config.toml", "MC_ADMIN_ENV=/data/empty.env", "CGROUP_PATH=/cgroup",
	}
	for _, p := range environment.Get[*environment.Recipe](env, "recipe").Providers {
		if p.ID == "restic" {
			settings = append(settings, "RESTIC__REPOSITORY_PATH=/data/restic")
		}
	}
	envFile := filepath.Join(env.Dir, "deployment.env")
	if err := os.WriteFile(envFile, []byte(strings.Join(settings, "\n")+"\n"), 0600); err != nil {
		return err
	}
	if err := f.Journal.Track(env.ID, b.Name, ""); err != nil {
		return err
	}
	args := []string{"create", "--name", b.Name, "--label", platform.RunLabel + "=" + f.Journal.Manifest.RunID, "--label", platform.EnvLabel + "=" + env.ID,
		"--env-file", envFile, "--publish", "127.0.0.1::8000", "--pid", "host",
		"--mount", "type=bind,src=" + f.Journal.Docker.Socket + ",dst=/var/run/docker.sock",
		"--mount", "type=bind,src=" + env.Dir + ",dst=/data",
		"--mount", "type=bind,src=" + filepath.Join(env.Dir, "servers") + ",dst=" + filepath.Join(env.Dir, "servers"),
		"--mount", "type=bind,src=/sys/fs/cgroup,dst=/cgroup,readonly", f.Options.Image}
	if _, err := f.Journal.Docker.Run(ctx, args...); err != nil {
		return err
	}
	if _, err := f.Journal.Docker.Run(ctx, "start", b.Name); err != nil {
		return err
	}
	container, err := f.Journal.Docker.Inspect(ctx, b.Name)
	if err != nil {
		return err
	}
	if container == nil || len(container.NetworkSettings.Ports["8000/tcp"]) != 1 {
		return fmt.Errorf("backend has no unique published API port")
	}
	b.URL = "http://127.0.0.1:" + container.NetworkSettings.Ports["8000/tcp"][0].HostPort
	b.Admin = api.New(b.URL, env.Recorder)
	b.Admin.ResolveURL = func() string { return b.URL }
	b.Admin.Bearer = b.Master
	env.Defer(func(context.Context) error { b.Admin.Close(); return nil })
	if err = b.Ready(ctx); err != nil {
		return err
	}
	for _, role := range []string{"owner", "admin"} {
		if err = b.Admin.JSON(ctx, "POST", "/api/admin/users", map[string]any{"username": "e2e-" + role, "password": b.Password, "role": role}, nil, 200); err != nil {
			return err
		}
	}
	var modules struct {
		Modules map[string]any `json:"modules"`
	}
	if err = b.Admin.JSON(ctx, "GET", "/api/config/modules", nil, &modules, 200); err != nil {
		return err
	}
	for name := range modules.Modules {
		var module struct {
			Data any `json:"config_data"`
		}
		if err = b.Admin.JSON(ctx, "GET", "/api/config/modules/"+name, nil, &module, 200); err != nil {
			return err
		}
		b.Configs[name] = module.Data
	}
	env.Recorder.Event("backend_ready", map[string]any{"url": b.URL, "container": container.ID, "image": container.Image})
	var schema map[string]any
	if err = b.Admin.JSON(ctx, "GET", "/api/openapi.json", nil, &schema, 200); err != nil {
		return err
	}
	if err = evidence.WriteJSON(filepath.Join(f.Journal.Manifest.Directory, "environments", env.ID, "openapi.json"), schema); err != nil {
		return err
	}
	return nil
}

func (b *Backend) Ready(ctx context.Context) error {
	return api.Wait(ctx, 300*time.Millisecond, "backend HTTP and database readiness", func(ctx context.Context) (bool, error) {
		container, err := b.Docker.Inspect(ctx, b.Name)
		if err != nil {
			return false, err
		}
		if container == nil || !container.State.Running {
			return false, api.Permanent(fmt.Errorf("backend is not running: %+v", container))
		}
		if err = b.Admin.JSON(ctx, "GET", "/api/system/health", nil, nil, 200); err != nil {
			return false, err
		}
		if err = b.Admin.JSON(ctx, "GET", "/api/admin/users", nil, nil, 200); err != nil {
			return false, err
		}
		return true, nil
	})
}

func (b *Backend) Restart(ctx context.Context) error {
	if _, err := b.Docker.Run(ctx, "restart", "--time", "10", b.Name); err != nil {
		return err
	}
	container, err := b.Docker.Inspect(ctx, b.Name)
	if err != nil {
		return err
	}
	if container == nil || len(container.NetworkSettings.Ports["8000/tcp"]) != 1 {
		return fmt.Errorf("restarted backend has no published port")
	}
	b.URL = "http://127.0.0.1:" + container.NetworkSettings.Ports["8000/tcp"][0].HostPort
	return b.Ready(ctx)
}

func verifyBackend(ctx context.Context, env *environment.Environment) error {
	b := BackendOf(env)
	if err := b.Admin.JSON(ctx, "GET", "/api/system/health", nil, nil, 200); err != nil {
		return err
	}
	var users []struct {
		Username string `json:"username"`
	}
	if err := b.Admin.JSON(ctx, "GET", "/api/admin/users", nil, &users, 200); err != nil {
		return err
	}
	if len(users) != 2 {
		return fmt.Errorf("expected two fixture users, got %d", len(users))
	}
	var templates []json.RawMessage
	if err := b.Admin.JSON(ctx, "GET", "/api/templates/", nil, &templates, 200); err != nil {
		return err
	}
	if len(templates) != 0 {
		return fmt.Errorf("template cleanup left %d templates", len(templates))
	}
	var servers []struct {
		ID string `json:"id"`
	}
	if err := b.Admin.JSON(ctx, "GET", "/api/servers/", nil, &servers, 200); err != nil {
		return err
	}
	if len(servers) != len(b.ServerIDs) {
		return fmt.Errorf("server inventory changed: got %v, expected %v", servers, b.ServerIDs)
	}
	for _, server := range servers {
		found := false
		for _, id := range b.ServerIDs {
			if server.ID == id {
				found = true
			}
		}
		if !found {
			return fmt.Errorf("unexpected server %s", server.ID)
		}
	}
	var tasks struct {
		Total int `json:"total"`
	}
	if err := b.Admin.JSON(ctx, "GET", "/api/tasks?active_only=true", nil, &tasks, 200); err != nil {
		return err
	}
	if tasks.Total != 0 {
		return fmt.Errorf("environment has %d active tasks", tasks.Total)
	}
	for name, initial := range b.Configs {
		var module struct {
			Data any `json:"config_data"`
		}
		if err := b.Admin.JSON(ctx, "GET", "/api/config/modules/"+name, nil, &module, 200); err != nil {
			return err
		}
		if !reflect.DeepEqual(module.Data, initial) {
			return fmt.Errorf("dynamic config %s differs from baseline", name)
		}
	}
	return nil
}

func Session(ctx context.Context, scope *engine.Scope, role string) (*api.Client, error) {
	b := BackendOf(scope.Env)
	client := api.New(b.URL, scope.Recorder)
	client.ResolveURL = func() string { return b.URL }
	scope.Cleanup(func(context.Context) error { client.Close(); return nil })
	if role != "" {
		if err := client.Login(ctx, "e2e-"+role, b.Password); err != nil {
			return nil, err
		}
	}
	return client, nil
}
