package servers

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func configurationPartialFailure(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	base := "/api/servers/" + server.ID
	valid := strings.Replace(server.Compose, "    environment:\n", "    entrypoint: [/bin/sleep]\n    command: ['600']\n    healthcheck:\n      disable: true\n    environment:\n", 1)
	var accepted submittedConfiguration
	if err = t.Step("run an owned container without game downloads using the normal lifecycle API", func() error {
		if err := c.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": valid}, &accepted, 200); err != nil {
			return err
		}
		if err := stoppedConfigurationTask(ctx, c, server.ID, accepted.ID); err != nil {
			return err
		}
		if err := fixtures.Operation(ctx, c, server.ID, "up"); err != nil {
			return err
		}
		return fixtures.Status(ctx, c, server.ID, "running")
	}); err != nil {
		return err
	}
	before, err := readCompose(ctx, c, base)
	if err != nil {
		return err
	}
	invalid := strings.Replace(valid, "entrypoint: [/bin/sleep]", "entrypoint: [/mc-admin-e2e-no-such-executable]", 1)
	var outcome struct {
		ID        string `json:"task_id"`
		Status    string `json:"status"`
		Error     string `json:"error"`
		ErrorCode string `json:"error_code"`
	}
	var operation struct {
		State          string  `json:"state"`
		Phase          string  `json:"phase"`
		Changed        bool    `json:"data_changed"`
		WritersStopped bool    `json:"writers_stopped"`
		RunningIntent  *bool   `json:"running_intent"`
		Reason         *string `json:"recovery_reason"`
	}
	if err = t.Step("a real Docker start failure preserves the applied configuration and reports a failed task", func() error {
		if err := c.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": invalid, "expected_version": before.Version}, &accepted, 200); err != nil {
			return err
		}
		if err := api.Wait(ctx, 200*time.Millisecond, "failed configuration application", func(ctx context.Context) (bool, error) {
			if err := c.JSON(ctx, "GET", "/api/tasks/"+accepted.ID, nil, &outcome, 200); err != nil {
				return false, api.Permanent(err)
			}
			return outcome.Status == "completed" || outcome.Status == "failed" || outcome.Status == "cancelled", nil
		}); err != nil {
			return err
		}
		if outcome.Status != "failed" || outcome.Error == "" {
			return fmt.Errorf("failed Docker start did not become a visible failed task: %+v", outcome)
		}
		after, err := readCompose(ctx, c, base)
		if err != nil {
			return err
		}
		if after.YAML != invalid || after.Version == before.Version {
			return fmt.Errorf("partial application was hidden or incorrectly advertised as a rollback")
		}
		if err := c.JSON(ctx, "GET", "/api/operations/"+accepted.ID, nil, &operation, 200); err != nil {
			return err
		}
		if (operation.State != "failed" && operation.State != "interrupted") || !operation.Changed || operation.RunningIntent == nil || !*operation.RunningIntent {
			return fmt.Errorf("partial operation lost its failure, data impact or original running intent: %+v", operation)
		}
		var status struct {
			Status string `json:"status"`
		}
		if err := c.JSON(ctx, "GET", base+"/status", nil, &status, 200); err != nil {
			return err
		}
		if !strings.EqualFold(status.Status, "created") && !strings.EqualFold(status.Status, "exists") {
			return fmt.Errorf("failed container start unexpectedly left the server running: %s", status.Status)
		}
		if !operation.WritersStopped {
			return c.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": valid}, nil, 423)
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("down and explicit recovery permit a repaired configuration while preserving the stopped intent", func() error {
		failedID := accepted.ID
		if err := fixtures.Operation(ctx, c, server.ID, "down"); err != nil {
			return err
		}
		if operation.Reason != nil || !operation.WritersStopped {
			if err := c.JSON(ctx, "POST", "/api/operations/"+failedID+"/resolve", map[string]string{"action": "configuration_reconciled"}, nil, 200); err != nil {
				return err
			}
		}
		current, err := readCompose(ctx, c, base)
		if err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": valid, "expected_version": current.Version}, &accepted, 200); err != nil {
			return err
		}
		if err := stoppedConfigurationTask(ctx, c, server.ID, accepted.ID); err != nil {
			return err
		}
		repaired, err := readCompose(ctx, c, base)
		if err != nil {
			return err
		}
		if repaired.YAML != valid {
			return fmt.Errorf("recovery did not retain the repaired configuration")
		}
		if err := c.JSON(ctx, "GET", "/api/tasks/"+failedID, nil, &outcome, 200); err != nil {
			return err
		}
		if outcome.Status != "failed" {
			return fmt.Errorf("recovery rewrote the original failed task outcome")
		}
		return nil
	})
}
