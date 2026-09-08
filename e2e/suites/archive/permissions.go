package archive

import (
	"context"
	"crypto/sha256"
	"fmt"
	"net/http"
	"net/url"
	"reflect"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func taskPermissions(ctx context.Context, t *engine.Scope) error {
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
	invalid, err := fixtures.Session(ctx, t, "")
	if err != nil {
		return err
	}
	u, err := url.Parse(invalid.URL() + "/api/tasks")
	if err != nil {
		return err
	}
	invalid.HTTP.Jar.SetCookies(u, []*http.Cookie{{Name: "mc_admin_session", Value: "invalid-task-session", Path: "/api"}})
	ownerWithoutCSRF, adminWithoutCSRF := *owner, *admin
	ownerWithoutCSRF.CSRF, adminWithoutCSRF.CSRF = false, false
	id := fixtures.ServerOf(t.Env).ID
	completedTask := func(client *api.Client) (string, error) {
		var submitted struct {
			ID string `json:"task_id"`
		}
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/files/ownership/restore", nil, &submitted, 200); err != nil {
			return "", err
		}
		_, err := client.Task(ctx, submitted.ID)
		return submitted.ID, err
	}
	completed, err := completedTask(owner)
	if err != nil {
		return err
	}
	var original map[string]any
	if err = owner.JSON(ctx, "GET", "/api/tasks/"+completed, nil, &original, 200); err != nil {
		return err
	}
	var input strings.Builder
	for n := 0; n < 260000; n++ {
		sum := sha256.Sum256([]byte(fmt.Sprintf("task-permissions-%d", n)))
		fmt.Fprintf(&input, "%x", sum)
	}
	for _, path := range []string{"/task-permissions.txt", "/task-cancel.txt"} {
		if err = fixtures.CreateFile(ctx, owner, id, path, input.String()); err != nil {
			return err
		}
	}
	startCompression := func(client *api.Client, path string) (string, error) {
		var submitted struct {
			ID string `json:"task_id"`
		}
		err := client.JSON(ctx, "POST", "/api/archive/compress", map[string]string{"server_id": id, "path": path}, &submitted, 200)
		return submitted.ID, err
	}
	if err = t.Step("anonymous, invalid-session and missing-CSRF requests cannot read or mutate tasks", func() error {
		active, err := startCompression(owner, "/task-permissions.txt")
		if err != nil {
			return err
		}
		var started api.Task
		if err := owner.JSON(ctx, "GET", "/api/tasks/"+active, nil, &started, 200); err != nil {
			return err
		}
		if started.Status != "pending" && started.Status != "running" {
			return fmt.Errorf("permission probes require an active compression, got %s", started.Status)
		}
		requests := []struct{ method, path string }{
			{"POST", "/api/tasks/" + active + "/cancel"},
			{"GET", "/api/tasks"},
			{"GET", "/api/tasks?active_only=true"},
			{"GET", "/api/tasks/" + active},
			{"DELETE", "/api/tasks/" + completed},
			{"DELETE", "/api/tasks"},
		}
		for _, requester := range []struct {
			name   string
			client *api.Client
			status int
		}{{"anonymous", anonymous, 401}, {"invalid session", invalid, 401}, {"owner without CSRF", &ownerWithoutCSRF, 403}, {"admin without CSRF", &adminWithoutCSRF, 403}} {
			for _, request := range requests {
				if requester.status == 403 && request.method == "GET" {
					continue
				}
				if err := requester.client.JSON(ctx, request.method, request.path, nil, nil, requester.status); err != nil {
					return fmt.Errorf("%s: %w", requester.name, err)
				}
			}
			var retained map[string]any
			if err := owner.JSON(ctx, "GET", "/api/tasks/"+completed, nil, &retained, 200); err != nil {
				return err
			}
			if !reflect.DeepEqual(original, retained) {
				return fmt.Errorf("%s changed the retained completed task", requester.name)
			}
		}
		result, err := owner.Task(ctx, active)
		if err != nil {
			return fmt.Errorf("rejected cancellation interfered with compression: %w", err)
		}
		filename, ok := result.Result["filename"].(string)
		if !ok || filename == "" {
			return fmt.Errorf("compression did not publish its archive")
		}
		response, err := owner.Do(ctx, "GET", "/api/archive/download?path="+url.QueryEscape(filename), nil, nil)
		if err != nil {
			return err
		}
		if err = owner.Expect(response, 200); err != nil {
			return err
		}
		if len(response.Body) < 6 || string(response.Body[:6]) != "7z\xbc\xaf\x27\x1c" {
			return fmt.Errorf("compression result is not a 7z archive")
		}
		return nil
	}); err != nil {
		return err
	}
	for _, principal := range []struct {
		name   string
		client *api.Client
	}{{"admin", admin}, {"owner", owner}} {
		if err = t.Step(principal.name+" can read, cancel, delete and clear actual tasks", func() error {
			client := principal.client
			finished, err := completedTask(client)
			if err != nil {
				return err
			}
			for _, path := range []string{"/api/tasks", "/api/tasks?active_only=true", "/api/tasks/" + finished} {
				if err := client.JSON(ctx, "GET", path, nil, nil, 200); err != nil {
					return err
				}
			}
			active, err := startCompression(client, "/task-cancel.txt")
			if err != nil {
				return err
			}
			if err := client.JSON(ctx, "POST", "/api/tasks/"+active+"/cancel", nil, nil, 200); err != nil {
				return err
			}
			if err = api.Wait(ctx, 100*time.Millisecond, "authenticated cancellation", func(ctx context.Context) (bool, error) {
				var task api.Task
				if err := client.JSON(ctx, "GET", "/api/tasks/"+active, nil, &task, 200); err != nil {
					return false, api.Permanent(err)
				}
				if task.Status == "completed" || task.Status == "failed" {
					return false, api.Permanent(fmt.Errorf("cancel requested but task ended %s", task.Status))
				}
				return task.Status == "cancelled", nil
			}); err != nil {
				return err
			}
			if err = client.JSON(ctx, "DELETE", "/api/tasks/"+active, nil, nil, 200); err != nil {
				return err
			}
			if err = client.JSON(ctx, "GET", "/api/tasks/"+active, nil, nil, 404); err != nil {
				return err
			}
			var cleared struct {
				Count int `json:"cleared"`
			}
			if err = client.JSON(ctx, "DELETE", "/api/tasks", nil, &cleared, 200); err != nil {
				return err
			}
			if cleared.Count < 1 {
				return fmt.Errorf("authenticated cleanup did not remove completed tasks")
			}
			var remaining struct {
				Total int `json:"total"`
			}
			if err := client.JSON(ctx, "GET", "/api/tasks", nil, &remaining, 200); err != nil {
				return err
			}
			if remaining.Total != 0 {
				return fmt.Errorf("authenticated cleanup left tasks")
			}
			return nil
		}); err != nil {
			return err
		}
	}
	return nil
}
