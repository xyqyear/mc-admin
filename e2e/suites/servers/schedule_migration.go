package servers

import (
	"context"
	"fmt"

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
	if err = c.JSON(ctx, "POST", "/api/servers/"+second, map[string]string{"yaml_content": compose}, nil, 200); err != nil {
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
 stamp=(datetime.datetime.fromisoformat(created)+datetime.timedelta(seconds=1)).isoformat()
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
	if err = t.Step("migration binds unambiguous history and reports duplicate plans without changing rows or executions", func() error {
		for _, sample := range []struct{ id, status, issue string }{
			{"legacy-duplicate-a", "active", "存在多个历史受管计划，无法确定唯一归属"},
			{"legacy-duplicate-b", "paused", "存在多个历史受管计划，无法确定唯一归属"},
			{"legacy-exact", "active", ""},
			{"legacy-independent", "active", ""},
		} {
			job, err := readScheduleIdentity(ctx, c, sample.id)
			if err != nil {
				return err
			}
			if job.Status != sample.status || job.Cron != "0 6 1 1 *" {
				return fmt.Errorf("migration rewrote retained schedule state: %+v", job)
			}
			if sample.issue != "" {
				if job.Generation != nil || job.Issue == nil || *job.Issue != sample.issue || job.Purpose == nil || *job.Purpose != "restart" {
					return fmt.Errorf("ambiguous plan was silently assigned or lacked a diagnosis: %+v", job)
				}
			} else if sample.id == "legacy-exact" {
				if job.Generation == nil || *job.Generation <= 0 || job.Issue != nil || job.Purpose == nil || *job.Purpose != "restart" {
					return fmt.Errorf("unambiguous historical plan lost its binding: %+v", job)
				}
			} else if job.Generation != nil || job.Purpose != nil || job.Issue != nil {
				return fmt.Errorf("independent historical task became managed: %+v", job)
			}
			var history []struct {
				ID       string   `json:"execution_id"`
				Status   string   `json:"status"`
				Messages []string `json:"messages"`
			}
			if err := c.JSON(ctx, "GET", "/api/cron/"+sample.id+"/executions", nil, &history, 200); err != nil {
				return err
			}
			if len(history) != 1 || history[0].ID != sample.id+"-history" || history[0].Status != "completed" || len(history[0].Messages) != 1 || history[0].Messages[0] != "retained legacy execution" {
				return fmt.Errorf("migration changed historical execution identity or outcome: %+v", history)
			}
		}
		var bound scheduleIdentity
		if err := c.JSON(ctx, "GET", "/api/servers/"+second+"/restart-schedule", nil, &bound, 200); err != nil {
			return err
		}
		if bound.ID != "legacy-exact" {
			return fmt.Errorf("server lookup did not retain the unambiguous legacy schedule")
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("ambiguous management is rejected until explicit cancellation and unrelated plans remain available", func() error {
		base := "/api/servers/" + first + "/restart-schedule"
		for _, action := range []struct{ method, suffix string }{{"GET", ""}, {"POST", ""}, {"POST", "/pause"}, {"POST", "/resume"}, {"DELETE", ""}} {
			if err := c.JSON(ctx, action.method, base+action.suffix, nil, nil, 409); err != nil {
				return err
			}
		}
		if err := c.JSON(ctx, "POST", "/api/cron/legacy-duplicate-b/resume", nil, nil, 409); err != nil {
			return err
		}
		for _, id := range []string{"legacy-duplicate-a", "legacy-duplicate-b"} {
			if err := c.JSON(ctx, "DELETE", "/api/cron/"+id, nil, nil, 200); err != nil {
				return err
			}
		}
		var created scheduleIdentity
		if err := c.JSON(ctx, "POST", base, map[string]string{"custom_cron": "0 7 1 1 *"}, &created, 200); err != nil {
			return err
		}
		if created.ID == "" || created.ID == "legacy-duplicate-a" || created.ID == "legacy-duplicate-b" {
			return fmt.Errorf("explicit repair reused an ambiguous task identity")
		}
		for _, id := range []string{"legacy-exact", "legacy-independent"} {
			job, err := readScheduleIdentity(ctx, c, id)
			if err != nil {
				return err
			}
			if job.Status != "active" || job.Cron != "0 6 1 1 *" {
				return fmt.Errorf("repair changed unrelated schedule: %+v", job)
			}
		}
		return nil
	})
}
