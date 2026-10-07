package servers

import (
	"context"
	"fmt"
	"slices"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
)

func scheduleMigration(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	first := fixtures.ServerOf(t.Env).ID
	second := first + "2"
	journal := environment.Get[*platform.Journal](t.Env, "journal")
	options := environment.Get[fixtures.Options](t.Env, "options")
	ports, err := platform.LeasePorts(ctx, journal.Docker, options.PortDirectory, 2)
	if err != nil {
		return err
	}
	t.Cleanup(func(context.Context) error { return ports.Close() })
	if err = journal.Track(t.Env.ID, "mc-"+second, "e2e-"+t.Env.ID); err != nil {
		return err
	}
	compose := fixtures.Compose(t.Env, second, fmt.Sprint(ports.Ports[0]), fmt.Sprint(ports.Ports[1]))
	if err = c.RunTask(ctx, "POST", "/api/servers/"+second, map[string]string{"yaml_content": compose}, nil); err != nil {
		return err
	}
	b := fixtures.BackendOf(t.Env)
	if _, err = b.Docker.Run(ctx, "stop", "--time", "10", b.Name); err != nil {
		return err
	}
	if _, err = fixtures.DeploymentCommand(ctx, t.Env, "schedule-downgrade", "alembic", "-c", "/app/alembic.ini", "downgrade", "2026092501"); err != nil {
		return err
	}
	const seed = `import datetime,json,sqlite3,sys
db=sqlite3.connect('/data/db.sqlite3')
first,second=sys.argv[1:]
for job_id,server,name,status in [('legacy-duplicate-a',first,'restart-'+first,'ACTIVE'),('legacy-duplicate-b',first,'restart-'+first,'PAUSED'),('legacy-exact',second,'restart-'+second,'ACTIVE'),('legacy-independent',first,'independent restart','ACTIVE')]:
 created=db.execute("SELECT created_at FROM server WHERE server_id=? AND status='ACTIVE'",(server,)).fetchone()[0]
 stamp=(datetime.datetime.fromisoformat(created)+datetime.timedelta(seconds=-1 if job_id=='legacy-exact' else 1)).isoformat()
 db.execute('INSERT INTO cronjob (cronjob_id,identifier,name,cron,second,params_json,execution_count,is_system,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(job_id,'restart_server',name,'0 6 1 1 *','0',json.dumps({'server_id':server}),1,False,status,stamp,stamp))
 db.execute('INSERT INTO cronjob_execution (cronjob_id,execution_id,started_at,ended_at,duration_ms,status,messages_json) VALUES (?,?,?,?,?,?,?)',(job_id,job_id+'-history',stamp,stamp,0,'COMPLETED','["retained legacy execution"]'))
db.commit()
db.close()
`
	if _, err = fixtures.DeploymentCommand(ctx, t.Env, "schedule-history-input", "python", "-c", seed, first, second); err != nil {
		return err
	}
	if err = b.Restart(ctx); err != nil {
		return err
	}
	if err = t.Step("startup preserves legacy plans and histories while registering exact logical targets", func() error {
		for _, sample := range []struct {
			id, status, target string
			managed            bool
		}{
			{"legacy-duplicate-a", "active", first, true},
			{"legacy-duplicate-b", "paused", first, true},
			{"legacy-exact", "active", second, true},
			{"legacy-independent", "active", first, false},
		} {
			job, err := readScheduleIdentity(ctx, c, sample.id)
			if err != nil {
				return err
			}
			name := "independent restart"
			if sample.managed {
				name = "restart-" + sample.target
			}
			registration := "registered"
			if sample.status == "paused" {
				registration = "inactive"
			}
			if job.ID != sample.id || job.Name != name || job.Identifier != "restart_server" || job.Params.ServerID != sample.target || job.Status != sample.status || job.Cron != "0 6 1 1 *" || job.Count != 1 || job.Registration != registration || job.RegistrationError != nil {
				return fmt.Errorf("migration rewrote a retained plan or prevented valid registration: %+v", job)
			}
			if sample.managed {
				if job.Purpose == nil || *job.Purpose != "restart" {
					return fmt.Errorf("migration discarded managed purpose: %+v", job)
				}
			} else if job.Purpose != nil {
				return fmt.Errorf("independent historical task became managed: %+v", job)
			}
			if err := checkLegacyScheduleHistory(ctx, c, sample.id); err != nil {
				return err
			}
		}
		for _, sample := range []struct{ server, id string }{{first, "legacy-duplicate-a"}, {second, "legacy-exact"}} {
			var selected scheduleIdentity
			if err := c.JSON(ctx, "GET", "/api/servers/"+sample.server+"/restart-schedule", nil, &selected, 200); err != nil {
				return err
			}
			if selected.ID != sample.id {
				return fmt.Errorf("server did not choose the oldest noncancelled exact-target plan: %+v", selected)
			}
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("duplicate plans remain independent and management selects oldest live then newest cancelled history", func() error {
		base := "/api/servers/" + first + "/restart-schedule"
		check := func(id, status, cron string) error {
			job, err := readScheduleIdentity(ctx, c, id)
			if err == nil && (job.Status != status || job.Cron != cron || job.Count != 1) {
				return fmt.Errorf("management unexpectedly changed another retained plan: %+v", job)
			}
			return err
		}
		selected := func(id, status string) error {
			var job scheduleIdentity
			if err := c.JSON(ctx, "GET", base, nil, &job, 200); err != nil {
				return err
			}
			if job.ID != id || job.Status != status {
				return fmt.Errorf("managed selection did not preserve the deterministic single-plan contract: %+v", job)
			}
			return nil
		}
		if err := c.JSON(ctx, "POST", base+"/pause", nil, nil, 200); err != nil {
			return err
		}
		if err := check("legacy-duplicate-a", "paused", "0 6 1 1 *"); err != nil {
			return err
		}
		if err := check("legacy-duplicate-b", "paused", "0 6 1 1 *"); err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", base+"/resume", nil, nil, 200); err != nil {
			return err
		}
		if err := selected("legacy-duplicate-a", "active"); err != nil {
			return err
		}
		if err := c.JSON(ctx, "DELETE", base, nil, nil, 200); err != nil {
			return err
		}
		if err := selected("legacy-duplicate-b", "paused"); err != nil {
			return err
		}
		if err := c.JSON(ctx, "DELETE", base, nil, nil, 200); err != nil {
			return err
		}
		if err := selected("legacy-duplicate-b", "cancelled"); err != nil {
			return err
		}
		for _, id := range []string{"legacy-exact", "legacy-independent"} {
			if err := check(id, "active", "0 6 1 1 *"); err != nil {
				return err
			}
		}
		if err := c.JSON(ctx, "POST", base+"/resume", nil, nil, 200); err != nil {
			return err
		}
		var updated scheduleIdentity
		if err := c.JSON(ctx, "POST", base, map[string]string{"custom_cron": "0 7 1 1 *"}, &updated, 200); err != nil {
			return err
		}
		if updated.ID != "legacy-duplicate-b" || updated.Name != "restart-"+first || updated.Status != "active" || updated.Cron != "0 7 1 1 *" {
			return fmt.Errorf("explicit re-enable or update replaced retained plan identity: %+v", updated)
		}
		if err := check("legacy-duplicate-a", "cancelled", "0 6 1 1 *"); err != nil {
			return err
		}
		var removed struct {
			IDs []string `json:"cancelled_restart_cronjob_ids"`
		}
		if err := c.RunTask(ctx, "POST", "/api/servers/"+first+"/operations", map[string]string{"action": "remove"}, &removed); err != nil {
			return err
		}
		slices.Sort(removed.IDs)
		if !slices.Equal(removed.IDs, []string{"legacy-duplicate-b", "legacy-independent"}) {
			return fmt.Errorf("removal cancelled plans outside the exact target or missed active plans: %v", removed.IDs)
		}
		for _, sample := range []struct{ id, status, cron string }{
			{"legacy-duplicate-a", "cancelled", "0 6 1 1 *"},
			{"legacy-duplicate-b", "cancelled", "0 7 1 1 *"},
			{"legacy-exact", "active", "0 6 1 1 *"},
			{"legacy-independent", "cancelled", "0 6 1 1 *"},
		} {
			if err := check(sample.id, sample.status, sample.cron); err != nil {
				return err
			}
			if err := checkLegacyScheduleHistory(ctx, c, sample.id); err != nil {
				return err
			}
		}
		return fixtures.Status(ctx, c, second, "exists")
	})
}

func checkLegacyScheduleHistory(ctx context.Context, c *api.Client, id string) error {
	rows, err := scheduleHistory(ctx, c, id)
	if err != nil {
		return err
	}
	if len(rows) != 1 || rows[0].ID != id+"-history" || rows[0].Status != "completed" || rows[0].Ended == nil || rows[0].Duration == nil || *rows[0].Duration != 0 || !slices.Equal(rows[0].Messages, []string{"retained legacy execution"}) {
		return fmt.Errorf("migration or management changed historical execution identity or outcome: %+v", rows)
	}
	return nil
}
