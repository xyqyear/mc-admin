package tasks

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"reflect"

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

func observeTaskEvents(ctx context.Context, client *api.Client, cursor string) *taskEventObserver {
	ctx, cancel := context.WithCancel(ctx)
	observer := &taskEventObserver{events: make(chan map[string]any, 256), done: make(chan struct{}), cancel: cancel}
	go func() {
		defer close(observer.done)
		path := "/api/tasks/events"
		if cursor != "" {
			path += "?operation_cursor=" + url.QueryEscape(cursor)
		}
		_, observer.err = client.SSEEvents(ctx, "GET", path, nil, "remove", func(event map[string]any) error {
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
	for _, field := range []string{"active_restorations", "prune_states"} {
		if _, ok := event[field].([]any); !ok {
			return fmt.Errorf("execution snapshot has no %s array", field)
		}
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
	for _, field := range []string{"task_id", "status", "progress", "progress_details", "server_id", "started_at", "ended_at", "error", "result"} {
		if _, present := task[field]; !present {
			return fmt.Errorf("task stream omits nullable or identity field %s", field)
		}
	}
	included, ok := task["result_included"].(bool)
	if !ok {
		return fmt.Errorf("task event omits explicit result inclusion")
	}
	if task["status"] == "pending" || task["status"] == "running" {
		if included || task["result"] != nil {
			return fmt.Errorf("unsettled task exposes a result")
		}
	} else if !included && task["result"] != nil {
		return fmt.Errorf("excluded terminal result is not null")
	}
	if included {
		encoded, err := json.Marshal(task["result"])
		if err != nil || len(encoded) > 16*1024 {
			return fmt.Errorf("included task result exceeds its JSON bound")
		}
	}
	return nil
}

func completedTaskEvent(ctx context.Context, observer *taskEventObserver, taskID string) (map[string]any, error) {
	for {
		event, err := observer.next(ctx, func(event map[string]any) bool {
			task, ok := event["task"].(map[string]any)
			return event["type"] == "upsert" && ok && task["task_id"] == taskID
		})
		if err != nil {
			return nil, err
		}
		task := event["task"].(map[string]any)
		if err = validateTaskSummary(task); err != nil {
			return nil, err
		}
		if task["status"] == "pending" || task["status"] == "running" {
			continue
		}
		if task["status"] != "completed" {
			return nil, fmt.Errorf("observed task ended unsuccessfully: %v", task["status"])
		}
		return task, nil
	}
}

func operationBatch(ctx context.Context, observer *taskEventObserver) (map[string]any, error) {
	event, err := observer.next(ctx, func(event map[string]any) bool { return event["type"] == "operation_changes" })
	if err != nil {
		return nil, err
	}
	batch, ok := event["changes"].(map[string]any)
	if !ok {
		return nil, fmt.Errorf("operation event has no changes object")
	}
	items, itemsOK := batch["items"].([]any)
	cursor, cursorOK := batch["next_cursor"].(string)
	more, moreOK := batch["has_more"].(bool)
	reset, resetOK := batch["reset_required"].(bool)
	active, activeOK := batch["active_count"].(float64)
	if !itemsOK || !cursorOK || cursor == "" || !moreOK || !resetOK || !activeOK || active < 0 || (reset && (len(items) != 0 || more)) {
		return nil, fmt.Errorf("operation event has invalid cursor/reset fields")
	}
	return batch, nil
}

func deletionEventResult(task map[string]any, path string) error {
	result, ok := task["result"].(map[string]any)
	if task["result_included"] != true || !ok || result["path"] != path {
		return fmt.Errorf("settled deletion event lacks its small authoritative result")
	}
	return nil
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
	first := observeTaskEvents(ctx, owner, "")
	defer first.close()
	second := observeTaskEvents(ctx, admin, "")
	defer second.close()
	var cursor string
	for _, observer := range []*taskEventObserver{first, second} {
		if err = currentTaskSnapshot(ctx, observer, ""); err != nil {
			return err
		}
		batch, err := operationBatch(ctx, observer)
		if err != nil {
			return err
		}
		if batch["reset_required"] != true {
			return fmt.Errorf("first operation observation did not reset")
		}
		if observer == first {
			cursor = batch["next_cursor"].(string)
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
		task, err := completedTaskEvent(ctx, observer, accepted.ID)
		if err != nil {
			return err
		}
		if err = deletionEventResult(task, "/sse-owned.txt"); err != nil {
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
	if err = fixtures.CreateFile(ctx, owner, id, "/sse-reconnected.txt", "reconnected task bytes\n"); err != nil {
		return err
	}
	reconnected := observeTaskEvents(ctx, owner, cursor)
	defer reconnected.close()
	if err = currentTaskSnapshot(ctx, reconnected, accepted.ID); err != nil {
		return err
	}
	deleted, offlineCreated := false, false
	for !deleted || !offlineCreated {
		batch, err := operationBatch(ctx, reconnected)
		if err != nil {
			return err
		}
		if batch["reset_required"] != false {
			return fmt.Errorf("retained operation cursor unexpectedly reset")
		}
		for _, item := range batch["items"].([]any) {
			change, ok := item.(map[string]any)
			if ok && change["operation_id"] == accepted.ID && change["state"] == "succeeded" {
				deleted = true
			}
			if ok && change["kind"] == "file_create" && change["state"] == "succeeded" {
				resources, _ := change["resources"].([]any)
				for _, item := range resources {
					resource, ok := item.(map[string]any)
					if ok && resource["server_id"] == id && resource["path"] == "data/sse-reconnected.txt" {
						offlineCreated = true
					}
				}
			}
		}
	}
	if _, err = owner.Task(ctx, accepted.ID); err != nil {
		return fmt.Errorf("dismissal or reconnect lost retained detail: %w", err)
	}
	accepted, err = owner.StartTask(ctx, "DELETE", base+"/files?path=/sse-reconnected.txt", nil)
	if err != nil {
		return err
	}
	task, err := completedTaskEvent(ctx, reconnected, accepted.ID)
	if err != nil {
		return err
	}
	if err = deletionEventResult(task, "/sse-reconnected.txt"); err != nil {
		return err
	}
	if err = owner.JSON(ctx, "GET", base+"/files/content?path=/sse-reconnected.txt", nil, nil, 404); err != nil {
		return err
	}
	accepted, err = owner.StartTask(ctx, "POST", "/api/self-check/checks/dependency.binaries/run", nil)
	if err != nil {
		return err
	}
	task, err = completedTaskEvent(ctx, reconnected, accepted.ID)
	if err != nil {
		return err
	}
	details, ok := task["progress_details"].(map[string]any)
	if !ok || details["kind"] != "self_check" || details["completed_checks"] != float64(1) || details["total_checks"] != float64(1) {
		return fmt.Errorf("self-check event lacks structured completion counters")
	}
	findings, ok := details["findings"].([]any)
	runID, idOK := details["id"].(string)
	if !ok || len(findings) == 0 || !idOK || runID == "" {
		return fmt.Errorf("self-check event lacks current findings and run identity")
	}
	var run map[string]any
	if err = owner.JSON(ctx, "GET", "/api/self-check/runs/"+url.PathEscape(runID), nil, &run, 200); err != nil {
		return err
	}
	if !reflect.DeepEqual(findings, run["findings"]) {
		return fmt.Errorf("streamed self-check findings differ from the persisted run")
	}
	invalid := observeTaskEvents(ctx, owner, "broken-cursor")
	defer invalid.close()
	if err = currentTaskSnapshot(ctx, invalid, ""); err != nil {
		return err
	}
	batch, err := operationBatch(ctx, invalid)
	if err != nil {
		return err
	}
	if batch["reset_required"] != true {
		return fmt.Errorf("invalid operation continuation did not explicitly reset")
	}
	paths := []string{"sse-batch-a.txt", "sse-batch-b.txt"}
	for _, path := range paths {
		if err = fixtures.CreateFile(ctx, owner, id, "/"+path, "owned batch bytes\n"); err != nil {
			return err
		}
	}
	accepted, err = owner.StartTask(ctx, "POST", base+"/files/delete-batch", map[string]any{"paths": paths})
	if err != nil {
		return err
	}
	task, err = completedTaskEvent(ctx, reconnected, accepted.ID)
	if err != nil {
		return err
	}
	details, ok = task["progress_details"].(map[string]any)
	if !ok || !reflect.DeepEqual(details, map[string]any{
		"kind": "items", "processed": float64(2), "total": float64(2),
		"deleted": float64(2), "failed": float64(0), "pending": float64(0),
	}) {
		return fmt.Errorf("batch deletion event lacks settled item counters")
	}
	deletedResult, ok := task["result"].(map[string]any)
	if task["result_included"] != true || !ok || deletedResult["deleted"] != float64(2) || deletedResult["failed"] != float64(0) || deletedResult["pending"] != float64(0) {
		return fmt.Errorf("batch deletion event lacks its inline outcome")
	}
	items, ok := deletedResult["results"].([]any)
	if !ok || len(items) != len(paths) || !reflect.DeepEqual(deletedResult["paths"], []any{paths[0], paths[1]}) {
		return fmt.Errorf("batch deletion event loses selected paths or per-item results")
	}
	for index, item := range items {
		outcome, ok := item.(map[string]any)
		if !ok || outcome["path"] != paths[index] || outcome["status"] != "deleted" {
			return fmt.Errorf("batch deletion event reports an incorrect item outcome")
		}
		if err = owner.JSON(ctx, "GET", base+"/files/content?path="+url.QueryEscape(paths[index]), nil, nil, 404); err != nil {
			return err
		}
	}

	payload := []byte("owned SSE hash bytes\n")
	const filename = "sse-hash.zip"
	var upload struct {
		ID string `json:"upload_id"`
	}
	if err = owner.JSON(ctx, "POST", "/api/archive/upload/init", map[string]any{"filename": filename, "path": "/", "size": len(payload)}, &upload, 200); err != nil {
		return err
	}
	if upload.ID == "" {
		return fmt.Errorf("archive upload acceptance has no session identity")
	}
	uploadPath := "/api/archive/upload/" + url.PathEscape(upload.ID)
	uploadCancelled := false
	scope.Cleanup(func(cleanupCtx context.Context) error {
		if uploadCancelled {
			return nil
		}
		return owner.JSON(cleanupCtx, "DELETE", uploadPath, nil, nil, 204)
	})
	response, err := owner.Do(ctx, "PATCH", uploadPath, payload, http.Header{"Content-Type": {"application/octet-stream"}, "Upload-Offset": {"0"}})
	if err != nil {
		return err
	}
	if err = owner.Expect(response, 200); err != nil {
		return err
	}
	var uploaded struct {
		Offset   int  `json:"offset"`
		Complete bool `json:"complete"`
	}
	if err = json.Unmarshal(response.Body, &uploaded); err != nil {
		return err
	}
	if uploaded.Offset != len(payload) || !uploaded.Complete {
		return fmt.Errorf("archive upload did not retain all transmitted bytes")
	}
	accepted, err = owner.StartTask(ctx, "POST", uploadPath+"/sha256", nil)
	if err != nil {
		return err
	}
	task, err = completedTaskEvent(ctx, reconnected, accepted.ID)
	if err != nil {
		return err
	}
	details, ok = task["progress_details"].(map[string]any)
	if !ok || details["kind"] != "bytes" || details["loaded"] != float64(len(payload)) || details["total"] != float64(len(payload)) || details["filename"] != filename {
		return fmt.Errorf("archive hash event lacks complete transmitted-byte counters")
	}
	hashResult, ok := task["result"].(map[string]any)
	if task["result_included"] != true || !ok || hashResult["event_type"] != "complete" || hashResult["sha256"] != fmt.Sprintf("%x", sha256.Sum256(payload)) {
		return fmt.Errorf("archive hash event differs from the independent payload digest")
	}
	if err = owner.JSON(ctx, "DELETE", uploadPath, nil, nil, 204); err != nil {
		return err
	}
	uploadCancelled = true
	return owner.JSON(ctx, "HEAD", uploadPath, nil, nil, 404)
}
