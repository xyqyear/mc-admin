package minecraft

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
)

func scheduledRestart(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id
	docker := environment.Get[*platform.Journal](t.Env, "journal").Docker
	startedAt := func() (time.Time, error) {
		value, err := docker.Run(ctx, "inspect", "--format", "{{.State.StartedAt}}", "mc-"+id)
		if err != nil {
			return time.Time{}, err
		}
		return time.Parse(time.RFC3339Nano, value)
	}
	rcon := func(command string) (string, error) {
		var response struct {
			Output string `json:"output"`
		}
		err := c.JSON(ctx, "POST", base+"/rcon", map[string]string{"command": command}, &response, 200)
		return response.Output, err
	}
	before, err := startedAt()
	if err != nil {
		return err
	}
	const marker = "scheduled restart must preserve the world\n"
	if err = t.Step("persist a whitelist entry, scoreboard value and world marker", func() error {
		for _, command := range []string{"whitelist add e2escheduled", "scoreboard objectives add e2eschedule dummy", "scoreboard players set e2escheduled e2eschedule 37", "save-all flush"} {
			output, err := rcon(command)
			if err != nil {
				return err
			}
			if output == "" {
				return fmt.Errorf("empty game response for %q", command)
			}
		}
		return fixtures.CreateFile(ctx, c, id, "/world/e2e-scheduled-restart.txt", marker)
	}); err != nil {
		return err
	}
	var schedule struct {
		ID     string `json:"cronjob_id"`
		Server string `json:"server_id"`
		Cron   string `json:"cron"`
		Status string `json:"status"`
	}
	if err = t.Step("restart scheduling exposes an active job due within one minute", func() error {
		if err := c.JSON(ctx, "POST", base+"/restart-schedule", map[string]string{"custom_cron": "* * * * *"}, nil, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "GET", base+"/restart-schedule", nil, &schedule, 200); err != nil {
			return err
		}
		if schedule.ID == "" || schedule.Server != id || schedule.Cron != "* * * * *" || schedule.Status != "active" {
			return fmt.Errorf("invalid restart schedule: %+v", schedule)
		}
		var next struct {
			At time.Time `json:"next_run_time"`
		}
		if err := c.JSON(ctx, "GET", "/api/cron/"+schedule.ID+"/next-run-time", nil, &next, 200); err != nil {
			return err
		}
		if until := time.Until(next.At); until < -time.Second || until > 65*time.Second {
			return fmt.Errorf("restart is not due within one minute: %s", next.At)
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("the scheduler performs a real restart and records completed execution", func() error {
		waitCtx, cancel := context.WithTimeout(ctx, 100*time.Second)
		defer cancel()
		err := api.Wait(waitCtx, 500*time.Millisecond, "scheduled Minecraft restart", func(ctx context.Context) (bool, error) {
			var executions []struct {
				ID       string    `json:"execution_id"`
				Status   string    `json:"status"`
				Started  time.Time `json:"started_at"`
				Ended    time.Time `json:"ended_at"`
				Messages []string  `json:"messages"`
			}
			if err := c.JSON(ctx, "GET", "/api/cron/"+schedule.ID+"/executions?limit=1", nil, &executions, 200); err != nil {
				return false, api.Permanent(err)
			}
			if len(executions) == 0 {
				return false, nil
			}
			execution := executions[0]
			if execution.Status == "failed" || execution.Status == "cancelled" {
				return false, api.Permanent(fmt.Errorf("scheduled restart failed: %+v", execution))
			}
			if execution.Status != "completed" {
				return false, nil
			}
			if execution.ID == "" || execution.Started.IsZero() || execution.Ended.Before(execution.Started) || !strings.Contains(strings.Join(execution.Messages, "\n"), "重启完成") {
				return false, api.Permanent(fmt.Errorf("execution did not complete a server restart: %+v", execution))
			}
			return true, nil
		})
		if err != nil {
			return err
		}
		if err = c.JSON(ctx, "POST", base+"/restart-schedule/pause", nil, nil, 200); err != nil {
			return err
		}
		after, err := startedAt()
		if err != nil {
			return err
		}
		t.Recorder.Event("scheduled_restart", map[string]any{"before_started_at": before, "after_started_at": after, "cronjob_id": schedule.ID})
		if !after.After(before) {
			return fmt.Errorf("completed cron execution did not restart the Minecraft container: %s -> %s", before, after)
		}
		return fixtures.WaitStatus(ctx, c, id, "healthy")
	}); err != nil {
		return err
	}
	return t.Step("RCON and persistent game state survive the scheduled restart", func() error {
		for _, check := range []struct{ command, expected string }{{"whitelist list", "e2escheduled"}, {"scoreboard players get e2escheduled e2eschedule", "37"}} {
			output, err := rcon(check.command)
			if err != nil {
				return err
			}
			if !strings.Contains(output, check.expected) {
				return fmt.Errorf("scheduled restart lost state for %q: %s", check.command, output)
			}
		}
		return fixtures.CheckFile(ctx, c, id, "/world/e2e-scheduled-restart.txt", marker)
	})
}
