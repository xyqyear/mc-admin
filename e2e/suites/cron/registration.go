package cron

import (
	"context"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func registration(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	identifiers := []string{"e2e-invalid-type", "e2e-invalid-params"}
	for _, id := range identifiers {
		if err := client.JSON(ctx, "POST", "/api/cron/", request(id, "0 0 1 1 *", "0"), nil, 200); err != nil {
			return err
		}
	}
	backend := fixtures.BackendOf(t.Env)
	if _, err := backend.Docker.Run(ctx, "stop", "--time", "10", backend.Name); err != nil {
		return err
	}
	const seed = `import sqlite3
with sqlite3.connect('/data/db.sqlite3') as db:
 for identifier in ('e2e-invalid-type','e2e-invalid-params'):
  if db.execute('SELECT COUNT(*) FROM cronjob WHERE cronjob_id=?',(identifier,)).fetchone()[0]!=1: raise RuntimeError('owned API-created cron missing')
 db.execute("UPDATE cronjob SET identifier='fixture_removed_job_type' WHERE cronjob_id='e2e-invalid-type'")
 db.execute("UPDATE cronjob SET identifier='restart_server', params_json='{}' WHERE cronjob_id='e2e-invalid-params'")
`
	if _, err := fixtures.DeploymentCommand(ctx, t.Env, "invalid-cron-history", "python", "-c", seed); err != nil {
		return err
	}
	t.Recorder.Event("cron_definition_fixture", map[string]any{"ids": identifiers, "deployment": "stopped", "mutations": "removed type and incomplete restart params"})
	if err := backend.Restart(ctx); err != nil {
		return err
	}
	if err := t.Step("invalid persisted definitions remain visible while independent scheduler registrations work", func() error {
		var inventory []job
		if err := client.JSON(ctx, "GET", "/api/cron/", nil, &inventory, 200); err != nil {
			return err
		}
		for _, id := range identifiers {
			found := false
			for _, row := range inventory {
				if row.ID == id {
					found = true
					if row.Status != "active" || row.Registration != "failed" || row.RegistrationError == nil || !strings.Contains(*row.RegistrationError, "配置") {
						return fmt.Errorf("invalid definition lost desired state or safe registration failure: %+v", row)
					}
				}
			}
			if !found {
				return fmt.Errorf("invalid persisted definition disappeared from list: %s", id)
			}
			var detail job
			if err := client.JSON(ctx, "GET", "/api/cron/"+id, nil, &detail, 200); err != nil {
				return err
			}
			if detail.Registration != "failed" || detail.Status != "active" {
				return fmt.Errorf("detail differs from failed registration: %+v", detail)
			}
		}
		var system job
		if err := client.JSON(ctx, "GET", "/api/cron/system:self_check", nil, &system, 200); err != nil {
			return err
		}
		if system.Registration != "registered" || system.RegistrationError != nil {
			return fmt.Errorf("one invalid definition prevented independent registration: %+v", system)
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("repair and pause/resume operate on visible broken definitions without deleting their identity", func() error {
		for _, id := range identifiers {
			if err := client.JSON(ctx, "PUT", "/api/cron/"+id, request("", "0 0 1 1 *", "0"), nil, 200); err != nil {
				return err
			}
			var row job
			if err := client.JSON(ctx, "GET", "/api/cron/"+id, nil, &row, 200); err != nil {
				return err
			}
			if row.ID != id || row.Identifier != "backup" || row.Registration != "registered" || row.RegistrationError != nil {
				return fmt.Errorf("repaired definition did not register with original ID: %+v", row)
			}
			if err := client.JSON(ctx, "POST", "/api/cron/"+id+"/resume", nil, nil, 409); err != nil {
				return err
			}
			if err := client.JSON(ctx, "POST", "/api/cron/"+id+"/pause", nil, nil, 200); err != nil {
				return err
			}
			if err := client.JSON(ctx, "GET", "/api/cron/"+id, nil, &row, 200); err != nil {
				return err
			}
			if row.Status != "paused" || row.Registration != "inactive" {
				return fmt.Errorf("paused definition claims registration: %+v", row)
			}
			if err := client.JSON(ctx, "POST", "/api/cron/"+id+"/resume", nil, nil, 200); err != nil {
				return err
			}
			if err := client.JSON(ctx, "GET", "/api/cron/"+id, nil, &row, 200); err != nil {
				return err
			}
			if row.Status != "active" || row.Registration != "registered" {
				return fmt.Errorf("resume did not restore registration: %+v", row)
			}
		}
		return nil
	})
}
