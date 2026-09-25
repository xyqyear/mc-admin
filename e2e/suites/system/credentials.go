package system

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func configurationCredentialLogs(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id
	secret := backend.Password + "-configuration"
	t.Recorder.Redactor.Add(secret)
	var original struct {
		YAML string `json:"yaml_content"`
	}
	if err = client.JSON(ctx, "GET", base+"/compose", nil, &original, 200); err != nil {
		return err
	}
	var started struct {
		ID string `json:"task_id"`
	}
	malformed := "services:\n  mc:\n    environment:\n      RCON_PASSWORD: " + secret + "\n    invalid: ["
	if err = client.JSON(ctx, "POST", base+"/compose", map[string]any{"yaml_content": malformed}, &started, 200); err != nil {
		return err
	}
	if err = api.Wait(ctx, 50*time.Millisecond, "invalid configuration fails without exposing its contents", func(ctx context.Context) (bool, error) {
		var task api.Task
		if err := client.JSON(ctx, "GET", "/api/tasks/"+started.ID, nil, &task, 200); err != nil {
			return false, api.Permanent(err)
		}
		if task.Status == "pending" || task.Status == "running" {
			return false, nil
		}
		if task.Status != "failed" || task.Error == "" || strings.Contains(task.Error, secret) {
			return false, api.Permanent(fmt.Errorf("invalid configuration task has unsafe or incorrect terminal result"))
		}
		return true, nil
	}); err != nil {
		return err
	}
	valid := original.YAML + "\n# private configuration: " + secret + "\n"
	if err = client.JSON(ctx, "POST", base+"/compose", map[string]any{"yaml_content": valid}, &started, 200); err != nil {
		return err
	}
	if _, err = client.Task(ctx, started.ID); err != nil {
		return err
	}
	var saved struct {
		YAML string `json:"yaml_content"`
	}
	if err = client.JSON(ctx, "GET", base+"/compose", nil, &saved, 200); err != nil {
		return err
	}
	if saved.YAML != valid {
		return fmt.Errorf("valid private configuration did not persist")
	}
	if err = fixtures.CreateFile(ctx, client, id, "/private.properties", "rcon.password="+secret); err != nil {
		return err
	}
	if err = fixtures.CheckFile(ctx, client, id, "/private.properties", "rcon.password="+secret); err != nil {
		return err
	}
	var failure struct {
		Detail string `json:"detail"`
	}
	missingSnapshot := map[string]any{"snapshot_id": "missing-snapshot", "server_id": id, "paths": []string{"/private.properties"}}
	if err = client.JSON(ctx, "POST", "/api/snapshots/restore/preview", missingSnapshot, &failure, 500); err != nil {
		return err
	}
	if failure.Detail != "服务器内部错误，请稍后重试" {
		return fmt.Errorf("unexpected request error did not use the safe public message")
	}
	if _, err = client.SSE(ctx, "POST", "/api/snapshots/restore", missingSnapshot, "complete"); err == nil || err.Error() != "SSE error: 服务器内部错误，请稍后重试" {
		return fmt.Errorf("unexpected restore failure did not use the safe SSE error")
	}
	container, err := backend.Docker.Run(ctx, "logs", backend.Name)
	if err != nil {
		return err
	}
	application, err := os.ReadFile(filepath.Join(t.Env.Dir, "logs", "app.log"))
	if err != nil {
		return err
	}
	audit, err := os.ReadFile(filepath.Join(t.Env.Dir, "logs", "operations.log"))
	if err != nil {
		return err
	}
	for _, output := range []string{container, string(application), string(audit)} {
		if strings.TrimSpace(output) == "" {
			return fmt.Errorf("required log channel is empty")
		}
		for _, value := range []string{secret, backend.Password, backend.Master} {
			if strings.Contains(output, value) {
				return fmt.Errorf("configuration credential appeared in a deployed log channel")
			}
		}
	}
	seen := map[string]bool{}
	for _, line := range strings.Split(strings.TrimSpace(string(audit)), "\n") {
		var row struct {
			Status int            `json:"status_code"`
			Body   map[string]any `json:"request_body"`
		}
		if err = json.Unmarshal([]byte(line), &row); err != nil {
			return err
		}
		if row.Status != 200 {
			continue
		}
		for _, field := range []string{"yaml_content", "content"} {
			if value, exists := row.Body[field]; exists {
				if value != "***MASKED***" {
					return fmt.Errorf("opaque %s was not redacted in successful audit", field)
				}
				seen[field] = true
			}
		}
	}
	if !seen["yaml_content"] || !seen["content"] {
		return fmt.Errorf("successful configuration/file audit records are missing")
	}
	return nil
}
