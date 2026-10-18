package world

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/api"
)

type executionEvents struct {
	frames chan map[string]any
	done   chan struct{}
	cancel context.CancelFunc
	err    error
}

func observeExecutions(ctx context.Context, client *api.Client) *executionEvents {
	ctx, cancel := context.WithCancel(ctx)
	observer := &executionEvents{frames: make(chan map[string]any, 256), done: make(chan struct{}), cancel: cancel}
	go func() {
		defer close(observer.done)
		_, observer.err = client.SSEEvents(ctx, "GET", "/api/tasks/events", nil, "", func(frame map[string]any) error {
			if frame["type"] != "snapshot" && frame["type"] != "prune_state" && frame["type"] != "restoration_index" {
				return nil
			}
			select {
			case observer.frames <- frame:
				return nil
			case <-ctx.Done():
				return ctx.Err()
			}
		})
	}()
	return observer
}

func (observer *executionEvents) close() { observer.cancel(); <-observer.done }

func (observer *executionEvents) next(ctx context.Context, matches func(map[string]any) bool) (map[string]any, error) {
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	for {
		select {
		case frame := <-observer.frames:
			if matches(frame) {
				return frame, nil
			}
		case <-observer.done:
			return nil, fmt.Errorf("execution event observation ended: %v", observer.err)
		case <-ctx.Done():
			return nil, fmt.Errorf("execution event not received: %w", ctx.Err())
		}
	}
}

func (observer *executionEvents) initial(ctx context.Context) (map[string]any, error) {
	frame, err := observer.next(ctx, func(frame map[string]any) bool { return frame["type"] == "snapshot" })
	if err != nil {
		return nil, err
	}
	for _, field := range []string{"tasks", "active_restorations", "prune_states"} {
		if _, ok := frame[field].([]any); !ok {
			return nil, fmt.Errorf("initial execution snapshot omitted %s", field)
		}
	}
	return frame, nil
}

func pruneInFrame(frame map[string]any, serverID, previewID, availability string) map[string]any {
	rows, _ := frame["prune_states"].([]any)
	for _, raw := range rows {
		row, _ := raw.(map[string]any)
		preview, _ := row["preview"].(map[string]any)
		if row["server_id"] == serverID && preview["task_id"] == previewID && preview["availability"] == availability {
			return row
		}
	}
	return nil
}

func (observer *executionEvents) prune(ctx context.Context, serverID, previewID, availability string) (map[string]any, error) {
	frame, err := observer.next(ctx, func(frame map[string]any) bool {
		row := pruneInFrame(frame, serverID, previewID, availability)
		if row == nil {
			return false
		}
		if availability == "ready" {
			task, _ := row["preview_task"].(map[string]any)
			return task["status"] == "completed" && task["result_included"] == true
		}
		return true
	})
	if err != nil {
		return nil, fmt.Errorf("prune %s expected %s: %w", previewID, availability, err)
	}
	return pruneInFrame(frame, serverID, previewID, availability), nil
}

func (observer *executionEvents) restoration(ctx context.Context, restorationID, taskID, serverID string, present bool) error {
	_, err := observer.next(ctx, func(frame map[string]any) bool {
		if frame["type"] != "snapshot" && frame["type"] != "restoration_index" {
			return false
		}
		rows, _ := frame["active_restorations"].([]any)
		for _, raw := range rows {
			row, _ := raw.(map[string]any)
			if row["id"] != restorationID {
				continue
			}
			if !present || row["operation_id"] != taskID || (row["status"] != "pending" && row["status"] != "running") {
				return false
			}
			targets, _ := row["targets"].([]any)
			for _, target := range targets {
				value, _ := target.(map[string]any)
				generation, _ := value["generation"].(float64)
				if value["server_id"] == serverID && generation > 0 {
					return true
				}
			}
			return false
		}
		return !present
	})
	return err
}

func checkPruneProgress(row map[string]any, previewID string) error {
	task, _ := row["preview_task"].(map[string]any)
	details, _ := task["progress_details"].(map[string]any)
	processed, processedOK := details["regions_processed"].(float64)
	total, totalOK := details["regions_total"].(float64)
	result, _ := task["result"].(map[string]any)
	if task["task_id"] != previewID || task["status"] != "completed" || task["result_included"] != true || result["dry_run"] != true || details["kind"] != "regions" || !processedOK || !totalOK || processed < 0 || total <= 0 || processed > total {
		return fmt.Errorf("prune event lacks settled result or truthful region counters: %+v", task)
	}
	return nil
}
