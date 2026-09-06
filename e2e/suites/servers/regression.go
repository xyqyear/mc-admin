package servers

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func conversions(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	s := fixtures.ServerOf(t.Env)
	base := "/api/servers/" + s.ID
	var compose struct {
		YAML string `json:"yaml_content"`
	}
	if err = c.JSON(ctx, "GET", base+"/compose", nil, &compose, 200); err != nil {
		return err
	}
	if !strings.Contains(compose.YAML, s.ID) {
		return fmt.Errorf("compose misses server identity")
	}
	if err = c.JSON(ctx, "GET", base+"/template-config", nil, nil, 400); err != nil {
		return err
	}
	var mode struct {
		Based bool `json:"is_template_based"`
	}
	if err = c.JSON(ctx, "GET", base+"/template-config/preview", nil, &mode, 200); err != nil {
		return err
	}
	if mode.Based {
		return fmt.Errorf("direct server reported template mode")
	}
	if err = c.JSON(ctx, "POST", base+"/convert-to-direct", nil, nil, 400); err != nil {
		return err
	}
	var template struct {
		ID int `json:"id"`
	}
	definition := fixtures.TemplateDefinition(t.Env)
	if err = c.JSON(ctx, "POST", "/api/templates/", definition, &template, 201); err != nil {
		return err
	}
	var extracted struct {
		Values   map[string]any `json:"extracted_values"`
		Warnings []string       `json:"warnings"`
	}
	if err = c.JSON(ctx, "POST", base+"/extract-variables", map[string]int{"template_id": template.ID}, &extracted, 200); err != nil {
		return err
	}
	if extracted.Values["name"] != s.ID || extracted.Values["game_port"] != float64(s.GamePort) || len(extracted.Warnings) != 0 {
		return fmt.Errorf("incorrect extracted variables: %+v", extracted)
	}
	values := map[string]any{"name": s.ID, "game_port": s.GamePort, "rcon_port": s.RCONPort}
	input := map[string]any{"template_id": template.ID, "variable_values": values}
	var check struct {
		Rebuild bool `json:"requires_rebuild"`
	}
	if err = c.JSON(ctx, "POST", base+"/check-conversion", input, &check, 200); err != nil {
		return err
	}
	if check.Rebuild {
		return fmt.Errorf("identical compose requires rebuild")
	}
	var converted struct {
		ID      string `json:"task_id"`
		Skipped bool   `json:"skipped_rebuild"`
	}
	if err = c.JSON(ctx, "POST", base+"/convert-to-template", input, &converted, 200); err != nil {
		return err
	}
	if !converted.Skipped || converted.ID != "" {
		return fmt.Errorf("identical conversion did not skip rebuild")
	}
	if err = c.JSON(ctx, "GET", base+"/template-config/preview", nil, &mode, 200); err != nil {
		return err
	}
	if !mode.Based {
		return fmt.Errorf("converted server did not report template mode")
	}
	if err = c.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": s.Compose}, nil, 400); err != nil {
		return err
	}
	if err = c.JSON(ctx, "PUT", base+"/template-config", map[string]any{"variable_values": map[string]any{}}, nil, 400); err != nil {
		return err
	}
	var task struct {
		ID string `json:"task_id"`
	}
	if err = c.JSON(ctx, "PUT", base+"/template-config", map[string]any{"variable_values": values}, &task, 200); err != nil {
		return err
	}
	if _, err = c.Task(ctx, task.ID); err != nil {
		return err
	}
	if err = c.JSON(ctx, "PUT", fmt.Sprintf("/api/templates/%d", template.ID), map[string]string{"description": "live template edit"}, nil, 200); err != nil {
		return err
	}
	var config struct {
		Updated bool           `json:"has_template_update"`
		Deleted bool           `json:"template_deleted"`
		Values  map[string]any `json:"variable_values"`
	}
	if err = c.JSON(ctx, "GET", base+"/template-config", nil, &config, 200); err != nil {
		return err
	}
	if !config.Updated || config.Deleted || config.Values["name"] != s.ID {
		return fmt.Errorf("template live/snapshot state incorrect: %+v", config)
	}
	if err = c.JSON(ctx, "POST", base+"/convert-to-direct", nil, nil, 200); err != nil {
		return err
	}
	changed := strings.Replace(s.Compose, "MAX_MEMORY: 1G", "MAX_MEMORY: 768M", 1)
	if err = c.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": changed}, &task, 200); err != nil {
		return err
	}
	if _, err = c.Task(ctx, task.ID); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", base+"/compose", nil, &compose, 200); err != nil {
		return err
	}
	if !strings.Contains(compose.YAML, "768M") {
		return fmt.Errorf("compose rebuild did not persist memory")
	}
	if err = c.JSON(ctx, "POST", base+"/check-conversion", input, &check, 200); err != nil {
		return err
	}
	if !check.Rebuild {
		return fmt.Errorf("changed compose did not require rebuild")
	}
	if err = c.JSON(ctx, "POST", base+"/convert-to-template", input, &converted, 200); err != nil {
		return err
	}
	if converted.Skipped || converted.ID == "" {
		return fmt.Errorf("conversion did not submit rebuild")
	}
	if _, err = c.Task(ctx, converted.ID); err != nil {
		return err
	}
	if err = api.Wait(ctx, 100*time.Millisecond, "conversion metadata persisted", func(ctx context.Context) (bool, error) {
		response, err := c.Do(ctx, "GET", base+"/template-config", nil, nil)
		if err != nil {
			return false, api.Permanent(err)
		}
		if response.Status == 400 {
			return false, nil
		}
		return response.Status == 200, c.Expect(response, 200)
	}); err != nil {
		return err
	}
	if err = c.JSON(ctx, "DELETE", fmt.Sprintf("/api/templates/%d", template.ID), nil, nil, 204); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", base+"/template-config", nil, &config, 200); err != nil {
		return err
	}
	if !config.Deleted {
		return fmt.Errorf("snapshot did not report deleted live template")
	}
	for _, suffix := range []string{"extract-variables", "check-conversion", "convert-to-template"} {
		if err = c.JSON(ctx, "POST", base+"/"+suffix, map[string]any{"template_id": 999999, "variable_values": values}, nil, 404); err != nil {
			return err
		}
	}
	return nil
}

func schedules(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	s := fixtures.ServerOf(t.Env)
	base := "/api/servers/" + s.ID
	if err = fixtures.Operation(ctx, c, s.ID, "remove"); err != nil {
		return err
	}
	for _, body := range []map[string]any{{}, {"yaml_content": s.Compose, "template_id": 1}, {"template_id": 1}, {"template_id": 999999, "variable_values": map[string]any{}}, {"yaml_content": "services: {}"}} {
		expected := 400
		if body["template_id"] == 999999 {
			expected = 404
		}
		if err = c.JSON(ctx, "POST", base, body, nil, expected); err != nil {
			return err
		}
	}
	var created struct {
		Schedule string `json:"restart_cronjob_id"`
	}
	if err = c.JSON(ctx, "POST", base, map[string]any{"yaml_content": s.Compose, "restart_schedule": map[string]string{"custom_cron": "17 4 * * *"}}, &created, 200); err != nil {
		return err
	}
	if created.Schedule == "" {
		return fmt.Errorf("bundled restart schedule missing")
	}
	type schedule struct {
		ID     string `json:"cronjob_id"`
		Status string `json:"status"`
		Cron   string `json:"cron"`
		Next   any    `json:"next_run_time"`
	}
	var current schedule
	for _, stage := range []struct{ action, expected string }{{"pause", "paused"}, {"resume", "active"}} {
		if err = c.JSON(ctx, "POST", base+"/restart-schedule/"+stage.action, nil, nil, 200); err != nil {
			return err
		}
		if err = c.JSON(ctx, "GET", base+"/restart-schedule", nil, &current, 200); err != nil {
			return err
		}
		if current.Status != stage.expected || current.ID != created.Schedule {
			return fmt.Errorf("schedule %s state incorrect: %+v", stage.action, current)
		}
	}
	if err = c.JSON(ctx, "POST", base+"/restart-schedule", map[string]string{"custom_cron": "23 5 * * *"}, &current, 200); err != nil {
		return err
	}
	if current.ID != created.Schedule || current.Cron != "23 5 * * *" || current.Next == nil {
		return fmt.Errorf("schedule update recreated ID or lost next execution")
	}
	if err = c.JSON(ctx, "DELETE", base+"/restart-schedule", nil, nil, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", base+"/restart-schedule", nil, &current, 200); err != nil {
		return err
	}
	if current.Status != "cancelled" || current.Next != nil {
		return fmt.Errorf("deleted schedule remains runnable")
	}
	for _, action := range []string{"pause", "resume"} {
		if err = c.JSON(ctx, "POST", "/api/servers/missing/restart-schedule/"+action, nil, nil, 404); err != nil {
			return err
		}
	}
	if err = c.JSON(ctx, "DELETE", "/api/servers/missing/restart-schedule", nil, nil, 404); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", base+"/restart-schedule", map[string]any{}, &current, 200); err != nil {
		return err
	}
	if current.Cron == "" || current.Status != "active" {
		return fmt.Errorf("automatic restart schedule invalid")
	}
	var removed struct {
		IDs []string `json:"cancelled_restart_cronjob_ids"`
	}
	if err = c.JSON(ctx, "POST", base+"/operations", map[string]string{"action": "remove"}, &removed, 200); err != nil {
		return err
	}
	if len(removed.IDs) != 1 || removed.IDs[0] != current.ID {
		return fmt.Errorf("remove did not cancel restart schedule")
	}
	return c.JSON(ctx, "GET", base, nil, nil, 404)
}

func reconciliation(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	admin, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	s := fixtures.ServerOf(t.Env)
	original := filepath.Join(t.Env.Dir, "servers", s.ID)
	holding := filepath.Join(t.Env.Dir, "detached-server")
	if err = admin.JSON(ctx, "POST", "/api/servers/sync", map[string]any{}, nil, 403); err != nil {
		return err
	}
	type syncResult struct {
		Applied bool `json:"applied"`
		Preview []struct {
			ID     string `json:"server_id"`
			Action string `json:"action"`
		} `json:"preview"`
		Adopted []any `json:"adopted"`
		Removed []any `json:"removed"`
		Errors  []any `json:"errors"`
	}
	var result syncResult
	if err = c.JSON(ctx, "POST", "/api/servers/sync", map[string]bool{"dry_run": true}, &result, 200); err != nil {
		return err
	}
	if result.Applied || len(result.Preview) != 0 {
		return fmt.Errorf("aligned inventory has changes")
	}
	// Physical drift is the input to reconciliation; all database mutations use the public API.
	if err = os.Rename(original, holding); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/servers/sync", map[string]any{}, nil, 409); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/servers/sync", map[string]bool{"dry_run": true, "force": true}, &result, 200); err != nil {
		return err
	}
	if len(result.Preview) != 1 || result.Preview[0].ID != s.ID || result.Preview[0].Action != "deactivate" {
		return fmt.Errorf("drift preview incorrect: %+v", result)
	}
	if err = c.JSON(ctx, "POST", "/api/servers/sync", map[string]bool{"force": true}, &result, 200); err != nil {
		return err
	}
	if len(result.Removed) != 1 || len(result.Errors) != 0 || !result.Applied {
		return fmt.Errorf("deactivation failed: %+v", result)
	}
	if err = os.Rename(holding, original); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/servers/sync", map[string]bool{"dry_run": true}, &result, 200); err != nil {
		return err
	}
	if len(result.Preview) != 1 || result.Preview[0].Action != "adopt" {
		return fmt.Errorf("filesystem adoption not previewed")
	}
	if err = c.JSON(ctx, "POST", "/api/servers/sync", map[string]any{}, &result, 200); err != nil {
		return err
	}
	if len(result.Adopted) != 1 || len(result.Errors) != 0 {
		return fmt.Errorf("adoption failed: %+v", result)
	}
	var listed []struct {
		ID string `json:"id"`
	}
	if err = c.JSON(ctx, "GET", "/api/servers/", nil, &listed, 200); err != nil {
		return err
	}
	if len(listed) != 1 || listed[0].ID != s.ID {
		return fmt.Errorf("adopted server absent from database inventory")
	}
	return fixtures.Status(ctx, c, s.ID, "exists")
}
