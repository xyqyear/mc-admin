package cron

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(r fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "cron.configuration-and-weekdays", Suite: "cron", Tags: []string{"regression"}, Recipe: r.Base, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: configuration},
		{ID: "cron.execution-and-recovery", Suite: "cron", Tags: []string{"regression", "restic"}, Recipe: r.Backup, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: execution},
	}
}

type job struct {
	ID         string `json:"cronjob_id"`
	Identifier string `json:"identifier"`
	Name       string `json:"name"`
	Cron       string `json:"cron"`
	Status     string `json:"status"`
	System     bool   `json:"is_system"`
	Count      int    `json:"execution_count"`
}

func request(id, expression, second string) map[string]any {
	return map[string]any{"cronjob_id": id, "identifier": "backup", "params": map[string]any{"enable_forget": false}, "cron": expression, "second": second, "name": "E2E scheduled backup"}
}

func configuration(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	path := "/api/cron/e2e-calendar"
	if err = t.Step("cron registries expose real job parameter schemas and protected system schedule", func() error {
		var registrations []struct {
			ID     string         `json:"identifier"`
			Schema map[string]any `json:"parameter_schema"`
		}
		if err := c.JSON(ctx, "GET", "/api/cron/registered", nil, &registrations, 200); err != nil {
			return err
		}
		found := map[string]bool{}
		for _, r := range registrations {
			if len(r.Schema) == 0 {
				return fmt.Errorf("job %s missing schema", r.ID)
			}
			found[r.ID] = true
		}
		for _, name := range []string{"backup", "restart_server", "self_check"} {
			if !found[name] {
				return fmt.Errorf("missing registered job %s", name)
			}
		}
		var system job
		if err := c.JSON(ctx, "GET", "/api/cron/system:self_check", nil, &system, 200); err != nil {
			return err
		}
		if !system.System || system.Status != "active" || system.Identifier != "self_check" {
			return fmt.Errorf("invalid automatic self-check job")
		}
		for _, action := range []string{"pause", "resume"} {
			if err := c.JSON(ctx, "POST", "/api/cron/system:self_check/"+action, nil, nil, 409); err != nil {
				return err
			}
		}
		if err := c.JSON(ctx, "DELETE", "/api/cron/system:self_check", nil, nil, 409); err != nil {
			return err
		}
		change := request("", "0 0 * * *", "0")
		change["identifier"] = "restart_server"
		change["params"] = map[string]string{"server_id": "absent"}
		return c.JSON(ctx, "PUT", "/api/cron/system:self_check", change, nil, 409)
	}); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/cron/", request("e2e-calendar", "0 0 * * 0", "0"), nil, 200); err != nil {
		return err
	}
	var inventory []job
	if err = c.JSON(ctx, "GET", "/api/cron/?identifier=backup", nil, &inventory, 200); err != nil {
		return err
	}
	if len(inventory) != 1 || inventory[0].ID != "e2e-calendar" {
		return fmt.Errorf("explicit-ID upsert duplicated the cron job")
	}
	if err = c.JSON(ctx, "POST", "/api/cron/", map[string]any{"identifier": "self_check", "params": map[string]string{"scope": "global"}, "cron": "0 * * * *"}, nil, 409); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/cron/", request("e2e-calendar", "0 0 * * 0", "0"), nil, 200); err != nil {
		return err
	}
	if err = t.Step("numeric and named weekdays use conventional crontab numbering", func() error {
		for _, test := range []struct {
			weekday string
			allowed map[time.Weekday]bool
		}{{"0", map[time.Weekday]bool{time.Sunday: true}}, {"7", map[time.Weekday]bool{time.Sunday: true}}, {"1", map[time.Weekday]bool{time.Monday: true}}, {"SUN", map[time.Weekday]bool{time.Sunday: true}}, {"1-5/2", map[time.Weekday]bool{time.Monday: true, time.Wednesday: true, time.Friday: true}}} {
			expression := "0 0 * * " + test.weekday
			if err := c.JSON(ctx, "PUT", path, request("", expression, "0"), nil, 200); err != nil {
				return err
			}
			var stored job
			if err := c.JSON(ctx, "GET", path, nil, &stored, 200); err != nil {
				return err
			}
			if stored.Cron != expression {
				return fmt.Errorf("cron text was rewritten")
			}
			var next struct {
				At time.Time `json:"next_run_time"`
			}
			if err := c.JSON(ctx, "GET", path+"/next-run-time", nil, &next, 200); err != nil {
				return err
			}
			if next.At.IsZero() || !test.allowed[next.At.Weekday()] || next.At.Hour() != 0 || next.At.Minute() != 0 {
				return fmt.Errorf("weekday %s scheduled unexpected date %s", test.weekday, next.At)
			}
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("pause, resume, cancellation, filters and invalid inputs preserve lifecycle contracts", func() error {
		if err := c.JSON(ctx, "POST", path+"/pause", nil, nil, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", path+"/pause", nil, nil, 409); err != nil {
			return err
		}
		if err := c.JSON(ctx, "GET", path+"/next-run-time", nil, nil, 409); err != nil {
			return err
		}
		var jobs []job
		if err := c.JSON(ctx, "GET", "/api/cron/?identifier=backup&status=paused", nil, &jobs, 200); err != nil {
			return err
		}
		if len(jobs) != 1 || jobs[0].ID != "e2e-calendar" {
			return fmt.Errorf("paused filter differs from stored lifecycle")
		}
		if err := c.JSON(ctx, "POST", path+"/resume", nil, nil, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "DELETE", path, nil, nil, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "GET", "/api/cron/?status=cancelled", nil, &jobs, 200); err != nil {
			return err
		}
		if len(jobs) != 1 || jobs[0].Status != "cancelled" {
			return fmt.Errorf("cancelled job/history was not retained")
		}
		if err := c.JSON(ctx, "DELETE", path, nil, nil, 409); err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", path+"/resume", nil, nil, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "DELETE", path, nil, nil, 200); err != nil {
			return err
		}
		for _, bad := range []map[string]any{{"identifier": "missing", "params": map[string]any{}, "cron": "* * * * *"}, {"identifier": "restart_server", "params": map[string]any{}, "cron": "* * * * *"}, request("bad", "0 0 * * 8", "0"), request("bad", "invalid", "0")} {
			if err := c.JSON(ctx, "POST", "/api/cron/", bad, nil, 400); err != nil {
				return err
			}
		}
		for _, suffix := range []string{"", "/next-run-time", "/executions"} {
			if err := c.JSON(ctx, "GET", "/api/cron/missing"+suffix, nil, nil, 404); err != nil {
				return err
			}
		}
		return c.JSON(ctx, "GET", "/api/cron/?status=invalid", nil, nil, 422)
	})
}

func execution(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	path := "/api/cron/e2e-execution"
	if err = c.JSON(ctx, "POST", "/api/cron/", request("e2e-execution", "* * * * *", "*/10"), nil, 200); err != nil {
		return err
	}
	if err = t.Step("scheduler performs real Restic backup and persists execution history", func() error {
		return api.Wait(ctx, 250*time.Millisecond, "successful scheduled execution", func(ctx context.Context) (bool, error) {
			var rows []struct {
				ID       string     `json:"execution_id"`
				Status   string     `json:"status"`
				Ended    *time.Time `json:"ended_at"`
				Messages []string   `json:"messages"`
			}
			if err := c.JSON(ctx, "GET", path+"/executions?limit=1", nil, &rows, 200); err != nil {
				return false, api.Permanent(err)
			}
			if len(rows) == 0 {
				return false, nil
			}
			if rows[0].Status == "failed" || rows[0].Status == "cancelled" {
				return false, api.Permanent(fmt.Errorf("scheduled execution failed: %v", rows[0].Messages))
			}
			if rows[0].Status != "completed" {
				return false, nil
			}
			if rows[0].ID == "" || rows[0].Ended == nil || len(rows[0].Messages) == 0 {
				return false, api.Permanent(fmt.Errorf("completed execution missing result metadata"))
			}
			return true, nil
		})
	}); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", path+"/pause", nil, nil, 200); err != nil {
		return err
	}
	var snapshots struct {
		Snapshots []map[string]any `json:"snapshots"`
	}
	if err = c.JSON(ctx, "GET", "/api/snapshots", nil, &snapshots, 200); err != nil {
		return err
	}
	if len(snapshots.Snapshots) == 0 {
		return fmt.Errorf("completed backup did not create a Restic snapshot")
	}
	systemRequest := map[string]any{"identifier": "self_check", "params": map[string]string{"scope": "global"}, "cron": "* * * * *", "second": "*/2", "name": "E2E automatic health"}
	if err = c.JSON(ctx, "PUT", "/api/cron/system:self_check", systemRequest, nil, 200); err != nil {
		return err
	}
	if err = api.Wait(ctx, 250*time.Millisecond, "scheduled self-check run", func(ctx context.Context) (bool, error) {
		var history struct {
			Runs []struct {
				Trigger string `json:"trigger"`
			} `json:"runs"`
		}
		if err := c.JSON(ctx, "GET", "/api/self-check/runs", nil, &history, 200); err != nil {
			return false, api.Permanent(err)
		}
		for _, run := range history.Runs {
			if run.Trigger == "scheduled" {
				return true, nil
			}
		}
		return false, nil
	}); err != nil {
		return err
	}
	systemRequest["cron"] = "0 * * * *"
	systemRequest["second"] = "0"
	if err = c.JSON(ctx, "PUT", "/api/cron/system:self_check", systemRequest, nil, 200); err != nil {
		return err
	}
	if err = t.Step("backend restart preserves paused jobs, execution rows and scheduled self-check results", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		var recovered job
		if err := c.JSON(ctx, "GET", path, nil, &recovered, 200); err != nil {
			return err
		}
		if recovered.Status != "paused" || recovered.Count < 1 {
			return fmt.Errorf("scheduler persistence lost paused state or execution count: %+v", recovered)
		}
		var history struct {
			Runs []struct {
				Trigger string `json:"trigger"`
				Scope   string `json:"scope"`
			} `json:"runs"`
		}
		if err := c.JSON(ctx, "GET", "/api/self-check/runs?limit=100", nil, &history, 200); err != nil {
			return err
		}
		found := false
		for _, run := range history.Runs {
			found = found || (run.Trigger == "scheduled" && run.Scope == "full")
		}
		if !found {
			return fmt.Errorf("scheduled execution did not persist a self-check run")
		}
		if err := c.JSON(ctx, "POST", path+"/resume", nil, nil, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "GET", path+"/next-run-time", nil, nil, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "DELETE", path, nil, nil, 200); err != nil {
			return err
		}
		var rows []map[string]any
		if err := c.JSON(ctx, "GET", path+"/executions", nil, &rows, 200); err != nil {
			return err
		}
		if len(rows) == 0 {
			return fmt.Errorf("cancellation removed execution history")
		}
		for _, row := range rows {
			if strings.EqualFold(fmt.Sprint(row["status"]), "failed") {
				return fmt.Errorf("unexpected failed scheduled run")
			}
		}
		return nil
	}); err != nil {
		return err
	}
	return nil
}
