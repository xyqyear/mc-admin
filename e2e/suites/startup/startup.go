package startup

import (
	"context"
	"fmt"
	"reflect"
	"regexp"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

const baselineRevision = "f2ee81a56fee"

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "startup.empty-database-bootstrap", Suite: "startup", Tags: []string{"regression"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: time.Minute, Run: emptyDatabase},
		{ID: "startup.versioned-database-upgrade", Suite: "startup", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: versionedUpgrade},
		{ID: "startup.unknown-revision-refused", Suite: "startup", Tags: []string{"regression"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: time.Minute, Run: unknownRevision},
		{ID: "startup.unversioned-schema-refused", Suite: "startup", Tags: []string{"regression"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: time.Minute, Run: unversionedSchema},
	}
}

func alembic(ctx context.Context, t *engine.Scope, suffix string, args ...string) (string, error) {
	command := append([]string{"alembic", "-c", "/app/alembic.ini"}, args...)
	output, err := fixtures.DeploymentCommand(ctx, t.Env, suffix, command...)
	t.Recorder.Event("alembic", map[string]any{"arguments": args, "output": output})
	return output, err
}

func revision(output string) (string, error) {
	pattern := regexp.MustCompile(`(?m)^([A-Za-z0-9_-]+)(?: \(head\))?$`)
	matches := pattern.FindAllStringSubmatch(output, -1)
	if len(matches) != 1 {
		return "", fmt.Errorf("expected one Alembic revision, got %q", output)
	}
	return matches[0][1], nil
}

func atHead(ctx context.Context, t *engine.Scope) error {
	output, err := alembic(ctx, t, "heads", "heads")
	if err != nil {
		return err
	}
	head, err := revision(output)
	if err != nil {
		return err
	}
	output, err = alembic(ctx, t, "current", "current")
	if err != nil {
		return err
	}
	current, err := revision(output)
	if err != nil {
		return err
	}
	if current != head {
		return fmt.Errorf("database revision %s differs from shipped head %s", current, head)
	}
	return nil
}

func emptyDatabase(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	return t.Step("fresh deployment bootstraps and stamps its private empty database", func() error {
		if err := atHead(ctx, t); err != nil {
			return err
		}
		var users []map[string]any
		if err := c.JSON(ctx, "GET", "/api/admin/users", nil, &users, 200); err != nil {
			return err
		}
		if len(users) != 2 {
			return fmt.Errorf("fresh database bootstrap did not retain both API-created users")
		}
		for _, path := range []string{"/api/config/modules", "/api/cron/", "/api/self-check/status", "/api/self-check/runs"} {
			if err := c.JSON(ctx, "GET", path, nil, nil, 200); err != nil {
				return err
			}
		}
		return nil
	})
}

func versionedUpgrade(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	var beforeUsers, afterUsers []map[string]any
	if err = c.JSON(ctx, "GET", "/api/admin/users", nil, &beforeUsers, 200); err != nil {
		return err
	}
	var config struct {
		Data map[string]any `json:"config_data"`
	}
	if err = c.JSON(ctx, "GET", "/api/config/modules/world", nil, &config, 200); err != nil {
		return err
	}
	config.Data["dimension_labels"] = map[string]any{".": "migration preserved world"}
	if err = c.JSON(ctx, "PUT", "/api/config/modules/world", map[string]any{"config_data": config.Data}, nil, 200); err != nil {
		return err
	}
	if err = t.Step("stop deployment and prepare the supported versioned baseline using shipped Alembic", func() error {
		if _, err := backend.Docker.Run(ctx, "stop", "--time", "10", backend.Name); err != nil {
			return err
		}
		if _, err := alembic(ctx, t, "downgrade", "downgrade", baselineRevision); err != nil {
			return err
		}
		output, err := alembic(ctx, t, "baseline", "current")
		if err != nil {
			return err
		}
		current, err := revision(output)
		if err != nil {
			return err
		}
		if current != baselineRevision {
			return fmt.Errorf("downgrade did not produce requested baseline: %s", current)
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("normal startup upgrades to shipped head and preserves public API data", func() error {
		if err := backend.Restart(ctx); err != nil {
			return err
		}
		if err := atHead(ctx, t); err != nil {
			return err
		}
		if err := c.JSON(ctx, "GET", "/api/user/me", nil, nil, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "GET", "/api/admin/users", nil, &afterUsers, 200); err != nil {
			return err
		}
		if !reflect.DeepEqual(beforeUsers, afterUsers) {
			return fmt.Errorf("startup upgrade altered user records")
		}
		var persisted struct {
			Data map[string]any `json:"config_data"`
		}
		if err := c.JSON(ctx, "GET", "/api/config/modules/world", nil, &persisted, 200); err != nil {
			return err
		}
		if !reflect.DeepEqual(config.Data, persisted.Data) {
			return fmt.Errorf("startup upgrade altered dynamic configuration")
		}
		if err := c.JSON(ctx, "GET", "/api/servers/"+fixtures.ServerOf(t.Env).ID, nil, nil, 200); err != nil {
			return err
		}
		for _, path := range []string{"/api/self-check/status", "/api/self-check/runs", "/api/cron/"} {
			if err := c.JSON(ctx, "GET", path, nil, nil, 200); err != nil {
				return err
			}
		}
		return nil
	})
}

func unknownRevision(ctx context.Context, t *engine.Scope) error {
	return refused(ctx, t, "unknown", "UPDATE alembic_version SET version_num = 'e2e_unknown_revision'", "Can't locate revision identified by 'e2e_unknown_revision'")
}

func unversionedSchema(ctx context.Context, t *engine.Scope) error {
	return refused(ctx, t, "unversioned", "DROP TABLE alembic_version", "Database schema exists but is not managed by Alembic")
}

func refused(ctx context.Context, t *engine.Scope, name, sql, diagnostic string) error {
	backend := fixtures.BackendOf(t.Env)
	if _, err := backend.Docker.Run(ctx, "stop", "--time", "10", backend.Name); err != nil {
		return err
	}
	if _, err := fixtures.DeploymentCommand(ctx, t.Env, "prepare-"+name, "python", "-c", "import sqlite3,sys; db=sqlite3.connect('/data/db.sqlite3'); db.execute(sys.argv[1]); db.commit(); db.close()", sql); err != nil {
		return err
	}
	return t.Step("unsupported schema makes the actual application process fail startup", func() error {
		if _, err := backend.Docker.Run(ctx, "start", backend.Name); err != nil {
			return err
		}
		exitCode := 0
		if err := api.Wait(ctx, 200*time.Millisecond, "application startup refusal", func(ctx context.Context) (bool, error) {
			container, err := backend.Docker.Inspect(ctx, backend.Name)
			if err != nil {
				return false, api.Permanent(err)
			}
			if container == nil {
				return false, api.Permanent(fmt.Errorf("deployment container disappeared"))
			}
			if container.State.Running {
				return false, nil
			}
			exitCode = container.State.ExitCode
			if exitCode == 0 {
				return false, api.Permanent(fmt.Errorf("invalid schema exited successfully"))
			}
			return true, nil
		}); err != nil {
			return err
		}
		logs, err := backend.Docker.Run(ctx, "logs", "--tail", "120", backend.Name)
		if err != nil {
			return err
		}
		t.Recorder.Event("startup_refusal", map[string]any{"exit_code": exitCode, "diagnostic": logs})
		if !strings.Contains(logs, diagnostic) || !strings.Contains(logs, "Application startup failed") {
			return fmt.Errorf("startup failed without required migration diagnostic %q", diagnostic)
		}
		return nil
	})
}
