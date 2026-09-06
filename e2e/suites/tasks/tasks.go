package tasks

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{{ID: "tasks.failure-filter-delete-clear", Suite: "tasks", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: history}}
}

func history(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	var started struct {
		ID string `json:"task_id"`
	}
	if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/populate", map[string]string{"archive_filename": "does-not-exist.zip"}, &started, 200); err != nil {
		return err
	}
	var failed struct {
		Status      string `json:"status"`
		Error       string `json:"error"`
		Cancellable bool   `json:"cancellable"`
		End         any    `json:"ended_at"`
	}
	if err = api.Wait(ctx, 100*time.Millisecond, "failed task terminal state", func(ctx context.Context) (bool, error) {
		if err := c.JSON(ctx, "GET", "/api/tasks/"+started.ID, nil, &failed, 200); err != nil {
			return false, api.Permanent(err)
		}
		return strings.EqualFold(failed.Status, "failed"), nil
	}); err != nil {
		return err
	}
	if failed.Error == "" || failed.End == nil || failed.Cancellable {
		return fmt.Errorf("failed task missing error, end time or cancellability contract: %+v", failed)
	}
	var listed struct {
		Total int              `json:"total"`
		Tasks []map[string]any `json:"tasks"`
	}
	if err = c.JSON(ctx, "GET", "/api/tasks?server_id="+id+"&status=failed", nil, &listed, 200); err != nil {
		return err
	}
	if listed.Total != 1 || listed.Tasks[0]["task_id"] != started.ID {
		return fmt.Errorf("failed task filter returned wrong rows")
	}
	if _, found := listed.Tasks[0]["result"]; found {
		return fmt.Errorf("summary contains result details")
	}
	if err = c.JSON(ctx, "GET", "/api/tasks?active_only=true", nil, &listed, 200); err != nil {
		return err
	}
	if listed.Total != 0 {
		return fmt.Errorf("failed task still active")
	}
	if err = c.JSON(ctx, "POST", "/api/tasks/"+started.ID+"/cancel", nil, nil, 400); err != nil {
		return err
	}
	if err = c.JSON(ctx, "DELETE", "/api/tasks/"+started.ID, nil, nil, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", "/api/tasks/"+started.ID, nil, nil, 404); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/files/ownership/restore", nil, &started, 200); err != nil {
		return err
	}
	if _, err = c.Task(ctx, started.ID); err != nil {
		return err
	}
	var cleared struct {
		Count int `json:"cleared"`
	}
	if err = c.JSON(ctx, "DELETE", "/api/tasks", nil, &cleared, 200); err != nil {
		return err
	}
	if cleared.Count != 1 {
		return fmt.Errorf("clear removed %d tasks, expected 1", cleared.Count)
	}
	if err = c.JSON(ctx, "GET", "/api/tasks", nil, &listed, 200); err != nil {
		return err
	}
	if listed.Total != 0 {
		return fmt.Errorf("task history not empty after clear")
	}
	if err = c.JSON(ctx, "DELETE", "/api/tasks/missing", nil, nil, 400); err != nil {
		return err
	}
	return c.JSON(ctx, "POST", "/api/tasks/missing/cancel", nil, nil, 400)
}
