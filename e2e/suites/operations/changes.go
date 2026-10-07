package operations

import (
	"context"
	"fmt"
	"net/url"
	"reflect"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type operationChange struct {
	Sequence  uint64     `json:"sequence"`
	ID        string     `json:"operation_id"`
	Kind      string     `json:"kind"`
	State     string     `json:"state"`
	Changed   bool       `json:"data_changed"`
	Updated   time.Time  `json:"updated_at"`
	Ended     *time.Time `json:"ended_at"`
	Resources []struct {
		Kind       string `json:"kind"`
		ServerID   string `json:"server_id"`
		Generation int    `json:"generation"`
		Path       string `json:"path"`
	} `json:"resources"`
}

type changePage struct {
	Items         []operationChange `json:"items"`
	Next          string            `json:"next_cursor"`
	More          bool              `json:"has_more"`
	Active        int               `json:"active_count"`
	ResetRequired bool              `json:"reset_required"`
}

func readChanges(ctx context.Context, client *api.Client, cursor string, limit int) (changePage, error) {
	query := url.Values{"limit": {fmt.Sprint(limit)}}
	if cursor != "" {
		query.Set("cursor", cursor)
	}
	var page changePage
	err := client.JSON(ctx, "GET", "/api/operations/changes?"+query.Encode(), nil, &page, 200)
	if err == nil && (page.Next == "" || page.Active < 0) {
		err = fmt.Errorf("invalid operation change continuation: %+v", page)
	}
	return page, err
}

func resetChanges(page changePage) error {
	if !page.ResetRequired || len(page.Items) != 0 || page.More {
		return fmt.Errorf("operation changes did not request an empty reset: %+v", page)
	}
	return nil
}

func drainChanges(ctx context.Context, client *api.Client, first changePage, limit int) ([]operationChange, string, error) {
	var changes []operationChange
	page := first
	var previous uint64
	for count := 0; count < 100; count++ {
		if page.ResetRequired || len(page.Items) > limit || (page.More && len(page.Items) == 0) {
			return nil, "", fmt.Errorf("operation change page cannot continue normally: %+v", page)
		}
		for _, change := range page.Items {
			if change.Sequence <= previous || change.ID == "" || change.Updated.IsZero() {
				return nil, "", fmt.Errorf("operation changes lost their order or identity: %+v", change)
			}
			previous = change.Sequence
			changes = append(changes, change)
		}
		if !page.More {
			return changes, page.Next, nil
		}
		next, err := readChanges(ctx, client, page.Next, limit)
		if err != nil {
			return nil, "", err
		}
		if next.Next == page.Next {
			return nil, "", fmt.Errorf("operation change pagination did not advance")
		}
		page = next
	}
	return nil, "", fmt.Errorf("operation change backlog exceeded the bounded scenario")
}

func fileChangeScope(change operationChange, serverID string, generation int) error {
	if len(change.Resources) != 1 {
		return fmt.Errorf("file notification lost its exact resource: %+v", change)
	}
	resource := change.Resources[0]
	if resource.Kind != "files" || resource.ServerID != serverID || resource.Generation != generation || resource.Path != "data/refresh-feed.txt" {
		return fmt.Errorf("file notification has the wrong server, generation or path: %+v", resource)
	}
	return nil
}

func scenarioFileChange(change operationChange, serverID string) bool {
	if change.Kind != "file_create" && change.Kind != "file_write" && change.Kind != "file_delete" {
		return false
	}
	for _, resource := range change.Resources {
		if resource.ServerID == serverID && resource.Path == "data/refresh-feed.txt" {
			return true
		}
	}
	return false
}

func incrementalRefresh(ctx context.Context, t *engine.Scope) error {
	owner, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	admin, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	anonymous, err := fixtures.Session(ctx, t, "")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id + "/files"
	var server struct {
		Generation int `json:"server_generation"`
	}
	if err = owner.JSON(ctx, "GET", "/api/servers/"+id, nil, &server, 200); err != nil {
		return err
	}
	if server.Generation <= 0 {
		return fmt.Errorf("API-created server has no current generation")
	}
	bootstrap, err := readChanges(ctx, owner, "", 200)
	if err != nil {
		return err
	}
	if err = resetChanges(bootstrap); err != nil {
		return err
	}
	if err = t.Step("feed reads require authentication and recover from an invalid continuation", func() error {
		if err := anonymous.JSON(ctx, "GET", "/api/operations/changes", nil, nil, 401); err != nil {
			return err
		}
		for _, limit := range []int{0, 1001} {
			if err := owner.JSON(ctx, "GET", fmt.Sprintf("/api/operations/changes?limit=%d", limit), nil, nil, 422); err != nil {
				return err
			}
		}
		reset, err := readChanges(ctx, admin, "invalid-operation-cursor", 200)
		if err != nil {
			return err
		}
		if err = resetChanges(reset); err != nil {
			return err
		}
		empty, err := readChanges(ctx, admin, reset.Next, 200)
		if err == nil && empty.ResetRequired {
			err = fmt.Errorf("new operation continuation could not be read: %+v", empty)
		}
		return err
	}); err != nil {
		return err
	}
	cursor := bootstrap.Next
	if err = t.Step("paginated file changes support stable replay and writes during catch-up", func() error {
		if err := fixtures.CreateFile(ctx, owner, id, "/refresh-feed.txt", "first committed content"); err != nil {
			return err
		}
		first, err := readChanges(ctx, owner, cursor, 1)
		if err != nil {
			return err
		}
		if first.ResetRequired || len(first.Items) != 1 || !first.More {
			return fmt.Errorf("file changes did not create a paginated backlog: %+v", first)
		}
		repeated, err := readChanges(ctx, admin, cursor, 1)
		if err != nil {
			return err
		}
		if !reflect.DeepEqual(repeated.Items, first.Items) {
			return fmt.Errorf("another session could not replay the same notification page: %+v / %+v", first, repeated)
		}
		if err = fixtures.WriteFile(ctx, owner, id, "/refresh-feed.txt", "committed while reading pages"); err != nil {
			return err
		}
		changes, continuation, err := drainChanges(ctx, admin, first, 1)
		if err != nil {
			return err
		}
		later, err := readChanges(ctx, admin, continuation, 1)
		if err != nil {
			return err
		}
		appended, continuation, err := drainChanges(ctx, admin, later, 1)
		if err != nil {
			return err
		}
		if len(appended) == 0 || appended[0].Sequence <= changes[len(changes)-1].Sequence {
			return fmt.Errorf("writes during pagination were skipped or reordered")
		}
		changes = append(changes, appended...)
		created := false
		writes := map[string]bool{}
		for _, change := range changes {
			if !scenarioFileChange(change, id) {
				continue
			}
			if err = fileChangeScope(change, id, server.Generation); err != nil {
				return err
			}
			if change.State == "succeeded" {
				if !change.Changed || change.Ended == nil {
					return fmt.Errorf("completed file change omitted its committed outcome: %+v", change)
				}
				created = created || change.Kind == "file_create"
				if change.Kind == "file_write" {
					writes[change.ID] = true
				}
			}
		}
		if !created || len(writes) != 2 {
			return fmt.Errorf("incremental feed lost committed file operations: create=%t writes=%d", created, len(writes))
		}
		cursor = continuation
		empty, err := readChanges(ctx, owner, cursor, 200)
		if err != nil {
			return err
		}
		unread, continuation, err := drainChanges(ctx, owner, empty, 200)
		if err != nil {
			return err
		}
		for _, change := range unread {
			if change.Sequence <= changes[len(changes)-1].Sequence || scenarioFileChange(change, id) {
				return fmt.Errorf("incremental observation repeated processed file notifications: %+v", change)
			}
		}
		cursor = continuation
		return fixtures.CheckFile(ctx, admin, id, "/refresh-feed.txt", "committed while reading pages")
	}); err != nil {
		return err
	}
	accepted, err := owner.StartTask(ctx, "DELETE", base+"?path=/refresh-feed.txt", nil)
	if err != nil {
		return err
	}
	task, err := admin.Task(ctx, accepted.ID)
	if err != nil {
		return err
	}
	if task.Result["path"] != "/refresh-feed.txt" {
		return fmt.Errorf("deletion task lost its business result: %+v", task)
	}
	if err = admin.JSON(ctx, "GET", base+"/content?path=/refresh-feed.txt", nil, nil, 404); err != nil {
		return err
	}
	stored, err := loadOperation(ctx, owner, accepted.ID)
	if err != nil {
		return err
	}
	if stored.State != "succeeded" || stored.Kind != "file_delete" || !stored.Changed || stored.Ended == nil {
		return fmt.Errorf("deletion task lacks its durable terminal operation: %+v", stored)
	}
	if err = t.Step("another session observes task acceptance and the actual deletion outcome", func() error {
		page, err := readChanges(ctx, admin, cursor, 1)
		if err != nil {
			return err
		}
		changes, continuation, err := drainChanges(ctx, admin, page, 1)
		if err != nil {
			return err
		}
		queued, completed := false, false
		for _, change := range changes {
			if change.ID != accepted.ID {
				continue
			}
			if change.Kind != "file_delete" {
				return fmt.Errorf("deletion notification changed its operation kind: %+v", change)
			}
			if err = fileChangeScope(change, id, server.Generation); err != nil {
				return err
			}
			queued = queued || change.State == "queued"
			completed = completed || (change.State == "succeeded" && change.Changed && change.Ended != nil)
		}
		if !queued || !completed {
			return fmt.Errorf("deletion notifications lost acceptance or completion: queued=%t completed=%t", queued, completed)
		}
		cursor = continuation
		return nil
	}); err != nil {
		return err
	}
	if err = owner.JSON(ctx, "DELETE", "/api/tasks/"+accepted.ID, nil, nil, 200); err != nil {
		return err
	}
	return t.Step("restart resets disposable notifications but retains operations and dismissed task results", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		reset, err := readChanges(ctx, admin, cursor, 200)
		if err != nil {
			return err
		}
		if err = resetChanges(reset); err != nil {
			return err
		}
		if reset.Next == cursor {
			return fmt.Errorf("backend restart retained the old notification instance")
		}
		retained, err := loadOperation(ctx, admin, accepted.ID)
		if err != nil {
			return err
		}
		if !reflect.DeepEqual(stored, retained) {
			return fmt.Errorf("restart changed the successful operation: %+v / %+v", stored, retained)
		}
		retainedTask, err := admin.Task(ctx, accepted.ID)
		if err != nil {
			return err
		}
		if !reflect.DeepEqual(task, retainedTask) {
			return fmt.Errorf("notification reset lost the dismissed task result: %+v / %+v", task, retainedTask)
		}
		if err = fixtures.CreateFile(ctx, owner, id, "/refresh-feed.txt", "new instance remains observable"); err != nil {
			return err
		}
		page, err := readChanges(ctx, admin, reset.Next, 200)
		if err != nil {
			return err
		}
		changes, _, err := drainChanges(ctx, admin, page, 200)
		if err != nil {
			return err
		}
		for _, change := range changes {
			if scenarioFileChange(change, id) && change.Kind == "file_write" && change.State == "succeeded" && change.Changed {
				if err = fileChangeScope(change, id, server.Generation); err != nil {
					return err
				}
				return fixtures.CheckFile(ctx, admin, id, "/refresh-feed.txt", "new instance remains observable")
			}
		}
		return fmt.Errorf("new backend instance did not publish subsequent file changes")
	})
}
