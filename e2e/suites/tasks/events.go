package tasks

import (
	"context"
	"fmt"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type taskEventObserver struct {
	events chan map[string]any
	done   chan struct{}
	cancel context.CancelFunc
	err    error
}

func observeTaskEvents(ctx context.Context, client *api.Client) *taskEventObserver {
	ctx, cancel := context.WithCancel(ctx)
	observer := &taskEventObserver{events: make(chan map[string]any, 256), done: make(chan struct{}), cancel: cancel}
	go func() {
		defer close(observer.done)
		_, observer.err = client.SSEEvents(ctx, "GET", "/api/tasks/events", nil, "remove", func(event map[string]any) error {
			select {
			case observer.events <- event:
				return nil
			case <-ctx.Done():
				return ctx.Err()
			}
		})
	}()
	return observer
}

func (observer *taskEventObserver) close() {
	observer.cancel()
	<-observer.done
}

func (observer *taskEventObserver) next(ctx context.Context, matches func(map[string]any) bool) (map[string]any, error) {
	for {
		select {
		case event := <-observer.events:
			if matches(event) {
				return event, nil
			}
		case <-observer.done:
			select {
			case event := <-observer.events:
				if matches(event) {
					return event, nil
				}
				continue
			default:
				return nil, fmt.Errorf("task event observation ended: %v", observer.err)
			}
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
}

func currentTaskSnapshot(ctx context.Context, observer *taskEventObserver, absentID string) error {
	event, err := observer.next(ctx, func(event map[string]any) bool { return event["type"] == "snapshot" })
	if err != nil {
		return err
	}
	tasks, ok := event["tasks"].([]any)
	if !ok {
		return fmt.Errorf("task snapshot has no task array")
	}
	for _, item := range tasks {
		task, ok := item.(map[string]any)
		if !ok {
			return fmt.Errorf("task snapshot contains a non-object")
		}
		if err := validateTaskSummary(task); err != nil {
			return err
		}
		if absentID != "" && task["task_id"] == absentID {
			return fmt.Errorf("dismissed task remains in reconnect snapshot")
		}
	}
	return nil
}

func validateTaskSummary(task map[string]any) error {
	if _, present := task["result"]; present {
		return fmt.Errorf("task stream broadcasts detailed results")
	}
	for _, field := range []string{"task_id", "status", "progress", "server_id", "started_at", "ended_at", "error"} {
		if _, present := task[field]; !present {
			return fmt.Errorf("task stream omits nullable or identity field %s", field)
		}
	}
	return nil
}

func completedTaskEvent(ctx context.Context, observer *taskEventObserver, taskID string) error {
	event, err := observer.next(ctx, func(event map[string]any) bool {
		task, ok := event["task"].(map[string]any)
		return event["type"] == "upsert" && ok && task["task_id"] == taskID &&
			(task["status"] == "completed" || task["status"] == "failed" || task["status"] == "cancelled")
	})
	if err != nil {
		return err
	}
	task := event["task"].(map[string]any)
	if task["status"] != "completed" {
		return fmt.Errorf("observed task ended unsuccessfully: %v", task["status"])
	}
	return validateTaskSummary(task)
}

func taskEvents(ctx context.Context, scope *engine.Scope) error {
	anonymous, err := fixtures.Session(ctx, scope, "")
	if err != nil {
		return err
	}
	if err = anonymous.JSON(ctx, "GET", "/api/tasks/events", nil, nil, 401); err != nil {
		return err
	}
	owner, err := fixtures.Session(ctx, scope, "owner")
	if err != nil {
		return err
	}
	admin, err := fixtures.Session(ctx, scope, "admin")
	if err != nil {
		return err
	}
	first := observeTaskEvents(ctx, owner)
	defer first.close()
	second := observeTaskEvents(ctx, admin)
	defer second.close()
	for _, observer := range []*taskEventObserver{first, second} {
		if err = currentTaskSnapshot(ctx, observer, ""); err != nil {
			return err
		}
	}
	id := fixtures.ServerOf(scope.Env).ID
	base := "/api/servers/" + id
	if err = fixtures.CreateFile(ctx, owner, id, "/sse-owned.txt", "task stream owned bytes\n"); err != nil {
		return err
	}
	accepted, err := owner.StartTask(ctx, "DELETE", base+"/files?path=/sse-owned.txt", nil)
	if err != nil {
		return err
	}
	for _, observer := range []*taskEventObserver{first, second} {
		if err = completedTaskEvent(ctx, observer, accepted.ID); err != nil {
			return err
		}
	}
	result, err := admin.Task(ctx, accepted.ID)
	if err != nil {
		return err
	}
	if result.Result["path"] != "/sse-owned.txt" {
		return fmt.Errorf("terminal task detail lacks the independent deletion result")
	}
	if err = admin.JSON(ctx, "GET", base+"/files/content?path=/sse-owned.txt", nil, nil, 404); err != nil {
		return err
	}
	first.close()
	if err = owner.JSON(ctx, "DELETE", "/api/tasks/"+accepted.ID, nil, nil, 200); err != nil {
		return err
	}
	if _, err = second.next(ctx, func(event map[string]any) bool {
		return event["type"] == "remove" && event["task_id"] == accepted.ID
	}); err != nil {
		return err
	}
	reconnected := observeTaskEvents(ctx, owner)
	defer reconnected.close()
	if err = currentTaskSnapshot(ctx, reconnected, accepted.ID); err != nil {
		return err
	}
	if _, err = owner.Task(ctx, accepted.ID); err != nil {
		return fmt.Errorf("dismissal or reconnect lost retained detail: %w", err)
	}
	if err = fixtures.CreateFile(ctx, owner, id, "/sse-reconnected.txt", "reconnected task bytes\n"); err != nil {
		return err
	}
	accepted, err = owner.StartTask(ctx, "DELETE", base+"/files?path=/sse-reconnected.txt", nil)
	if err != nil {
		return err
	}
	if err = completedTaskEvent(ctx, reconnected, accepted.ID); err != nil {
		return err
	}
	return owner.JSON(ctx, "GET", base+"/files/content?path=/sse-reconnected.txt", nil, nil, 404)
}
