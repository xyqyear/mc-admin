package cron

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func safeValidationErrors(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	const secret = "owned-cron-validation-sensitive-value"
	t.Recorder.Redactor.Add(secret)
	const id = "e2e-safe-cron-errors"
	if err = c.JSON(ctx, "POST", "/api/cron/", request(id, "0 0 1 1 *", "0"), nil, 200); err != nil {
		return err
	}
	for _, operation := range []struct{ method, path string }{
		{"POST", "/api/cron/"}, {"PUT", "/api/cron/" + id},
	} {
		for _, parameterFailure := range []bool{true, false} {
			body := request("e2e-rejected-cron", "0 0 1 1 *", "0")
			expected := "服务器内部错误，请稍后重试"
			if parameterFailure {
				body["params"] = map[string]any{"enable_forget": secret}
				expected = "任务参数无效: enable_forget: 应为布尔值"
			} else {
				body["second"] = secret
			}
			payload, err := json.Marshal(body)
			if err != nil {
				return err
			}
			response, err := c.Do(ctx, operation.method, operation.path, payload, http.Header{"Content-Type": {"application/json"}})
			if err != nil {
				return err
			}
			if err = c.Expect(response, 400); err != nil {
				return err
			}
			var failure struct {
				Detail string `json:"detail"`
			}
			if err = json.Unmarshal(response.Body, &failure); err != nil {
				return err
			}
			if failure.Detail != expected || strings.Contains(string(response.Body), secret) {
				return fmt.Errorf("cron rejection lost its safe field diagnostic or exposed submitted values")
			}
		}
	}
	var stored job
	if err = c.JSON(ctx, "GET", "/api/cron/"+id, nil, &stored, 200); err != nil {
		return err
	}
	if stored.ID != id || stored.Cron != "0 0 1 1 *" || stored.Name != "E2E scheduled backup" || stored.Registration != "registered" {
		return fmt.Errorf("rejected updates changed the existing stored cron or its registration")
	}
	if err = c.JSON(ctx, "GET", "/api/cron/e2e-rejected-cron", nil, nil, 404); err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	logs, err := backend.Docker.Run(ctx, "logs", backend.Name)
	if err != nil {
		return err
	}
	applicationLog, err := os.ReadFile(filepath.Join(t.Env.Dir, "logs", "app.log"))
	if err != nil {
		return err
	}
	for _, output := range []string{logs, string(applicationLog)} {
		if !strings.Contains(output, "Cron parameter validation failed: ValidationError") || strings.Contains(output, secret) {
			return fmt.Errorf("cron validation logs lack safe diagnostics or expose submitted values")
		}
	}
	return nil
}
