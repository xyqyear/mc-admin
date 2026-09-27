package tasks

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func management(ctx context.Context, t *engine.Scope) error {
	owner, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id
	if err = fixtures.CreateFile(ctx, owner, id, "/detached.txt", "owned task input"); err != nil {
		return err
	}
	started := time.Now()
	accepted, err := owner.StartTask(ctx, "DELETE", base+"/files?path=/detached.txt", nil)
	if err != nil {
		return err
	}
	if time.Since(started) > 5*time.Second {
		return fmt.Errorf("file task acceptance exceeded five seconds")
	}
	observer, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	task, err := observer.Task(ctx, accepted.ID)
	if err != nil {
		return err
	}
	if task.Result["path"] != "/detached.txt" {
		return fmt.Errorf("deletion task has no target result: %+v", task)
	}
	if err = observer.JSON(ctx, "GET", base+"/files/content?path=/detached.txt", nil, nil, 404); err != nil {
		return err
	}
	var operation struct{ State, Kind, Origin string }
	if err = owner.JSON(ctx, "GET", "/api/operations/"+accepted.ID, nil, &operation, 200); err != nil {
		return err
	}
	if operation.Kind != "file_delete" || operation.Origin != "task" || operation.State != "succeeded" {
		return fmt.Errorf("task lacks successful durable operation: %+v", operation)
	}
	if err = owner.RunTask(ctx, "POST", base+"/operations", map[string]string{"action": "down"}, nil); err != nil {
		return err
	}
	if err = owner.RunTask(ctx, "POST", base+"/operations", map[string]string{"action": "remove"}, nil); err != nil {
		return err
	}
	if err = fixtures.Status(ctx, owner, id, "removed"); err != nil {
		return err
	}
	return owner.RunTask(ctx, "POST", base, map[string]string{"yaml_content": fixtures.ServerOf(t.Env).Compose}, nil)
}
