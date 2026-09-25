package operations

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func interruptedHistory(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	taskID, cronExecutionID := "e2e-interrupted-task", "e2e-interrupted-cron"
	cronID := "e2e-paused-restart"
	if err = fixtures.CreateFile(ctx, client, id, "/recovery-marker.txt", "completed data must not be replayed"); err != nil {
		return err
	}
	if err = client.JSON(ctx, "POST", "/api/cron/", map[string]any{
		"cronjob_id": cronID, "identifier": "restart_server", "name": "E2E recovery paused restart",
		"params": map[string]string{"server_id": id}, "cron": "0 0 1 1 *",
	}, nil, 200); err != nil {
		return err
	}
	if err = client.JSON(ctx, "POST", "/api/cron/"+cronID+"/pause", nil, nil, 200); err != nil {
		return err
	}
	if err = prepareInterruptedHistory(ctx, t, []interruptedInput{
		{ID: taskID, Kind: "file_ownership_repair", Origin: "task", ServerID: id, Resource: "files", Changed: true},
		{ID: cronExecutionID, Kind: "restart_server", Origin: "cron", ServerID: id, Resource: "server", CronjobID: cronID},
	}); err != nil {
		return err
	}
	if err = fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
		return err
	}
	check := func() error {
		for _, operationID := range []string{taskID, cronExecutionID} {
			result, err := loadOperation(ctx, client, operationID)
			if err != nil {
				return err
			}
			if err = interrupted(result, operationID, id); err != nil {
				return err
			}
			if result.Reason != nil || result.CacheDegraded {
				return fmt.Errorf("confirmed stopped writers unexpectedly blocked the server: %+v", result)
			}
		}
		var task struct {
			ID          string     `json:"task_id"`
			Status      string     `json:"status"`
			Error       string     `json:"error"`
			Cancellable bool       `json:"cancellable"`
			Ended       *time.Time `json:"ended_at"`
		}
		if err := client.JSON(ctx, "GET", "/api/tasks/"+taskID, nil, &task, 200); err != nil {
			return err
		}
		if task.ID != taskID || task.Status != "failed" || !strings.Contains(task.Error, "中断") || task.Ended == nil || task.Cancellable {
			return fmt.Errorf("legacy task API lost interrupted history: %+v", task)
		}
		var active struct {
			Total int `json:"total"`
		}
		if err := client.JSON(ctx, "GET", "/api/tasks?active_only=true&server_id="+id, nil, &active, 200); err != nil {
			return err
		}
		if active.Total != 0 {
			return fmt.Errorf("interrupted task was replayed or left active")
		}
		var executions []struct {
			ID       string     `json:"execution_id"`
			Status   string     `json:"status"`
			Ended    *time.Time `json:"ended_at"`
			Messages []string   `json:"messages"`
			Duration *int       `json:"duration_ms"`
		}
		if err := client.JSON(ctx, "GET", "/api/cron/"+cronID+"/executions", nil, &executions, 200); err != nil {
			return err
		}
		if len(executions) != 1 || executions[0].ID != cronExecutionID || executions[0].Status != "failed" || executions[0].Ended == nil || !strings.Contains(strings.Join(executions[0].Messages, " "), "中断") || !strings.Contains(strings.Join(executions[0].Messages, " "), "E2E interrupted before completion") || executions[0].Duration == nil || *executions[0].Duration < 0 {
			return fmt.Errorf("cron interruption did not preserve its execution identity: %+v", executions)
		}
		var cron struct {
			Status       string `json:"status"`
			Count        int    `json:"execution_count"`
			Registration string `json:"registration_status"`
		}
		if err := client.JSON(ctx, "GET", "/api/cron/"+cronID, nil, &cron, 200); err != nil {
			return err
		}
		if cron.Status != "paused" || cron.Count != 1 || cron.Registration != "inactive" {
			return fmt.Errorf("startup replayed or resumed the paused cron job: %+v", cron)
		}
		if err := fixtures.Status(ctx, client, id, "exists"); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/recovery-marker.txt", "completed data must not be replayed")
	}
	if err = t.Step("startup settles task and cron histories before exposing write APIs", check); err != nil {
		return err
	}
	return t.Step("a second restart preserves terminal identities and never replays the writes", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		return check()
	})
}
