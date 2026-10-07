package servers

import (
	"context"
	"encoding/json"
	"fmt"
	"slices"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type scheduleIdentity struct {
	ID                string  `json:"cronjob_id"`
	Name              string  `json:"name"`
	Identifier        string  `json:"identifier"`
	Status            string  `json:"status"`
	Cron              string  `json:"cron"`
	Purpose           *string `json:"managed_purpose"`
	Registration      string  `json:"registration_status"`
	RegistrationError *string `json:"registration_error"`
	Count             int     `json:"execution_count"`
	Params            struct {
		ServerID string `json:"server_id"`
	} `json:"params"`
}

func readScheduleIdentity(ctx context.Context, c *api.Client, id string) (scheduleIdentity, error) {
	var result scheduleIdentity
	var raw json.RawMessage
	if err := c.JSON(ctx, "GET", "/api/cron/"+id, nil, &raw, 200); err != nil {
		return result, err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		return result, err
	}
	for _, removed := range []string{"managed_server_generation", "managed_binding_issue"} {
		if _, present := fields[removed]; present {
			return result, fmt.Errorf("cron detail still exposes removed binding field %s", removed)
		}
	}
	err := json.Unmarshal(raw, &result)
	return result, err
}

type scheduleExecution struct {
	ID       string     `json:"execution_id"`
	Status   string     `json:"status"`
	Ended    *time.Time `json:"ended_at"`
	Duration *int       `json:"duration_ms"`
	Messages []string   `json:"messages"`
}

func scheduleHistory(ctx context.Context, c *api.Client, id string) ([]scheduleExecution, error) {
	var rows []scheduleExecution
	err := c.JSON(ctx, "GET", "/api/cron/"+id+"/executions", nil, &rows, 200)
	return rows, err
}

func waitScheduleSkip(ctx context.Context, c *api.Client, id, reason string, previous []scheduleExecution) (scheduleExecution, error) {
	var observed scheduleExecution
	seen := make(map[string]bool, len(previous))
	for _, row := range previous {
		seen[row.ID] = true
	}
	waitCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	err := api.Wait(waitCtx, 200*time.Millisecond, "scheduled restart skip: "+reason, func(ctx context.Context) (bool, error) {
		rows, err := scheduleHistory(ctx, c, id)
		if err != nil {
			return false, api.Permanent(err)
		}
		for _, row := range rows {
			if seen[row.ID] || row.Status == "running" {
				continue
			}
			if row.Status != "skipped" || row.ID == "" || row.Ended == nil || row.Duration == nil || *row.Duration < 0 || !strings.Contains(strings.Join(row.Messages, "\n"), reason) {
				return false, api.Permanent(fmt.Errorf("restart did not retain the expected skip reason and terminal metadata: %+v", row))
			}
			observed = row
			return true, nil
		}
		return false, nil
	})
	return observed, err
}

func scheduleLogicalTarget(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	base := "/api/servers/" + server.ID
	var incarnation struct {
		Generation int `json:"server_generation"`
	}
	if err = c.JSON(ctx, "GET", base, nil, &incarnation, 200); err != nil {
		return err
	}
	var independent scheduleIdentity
	if err = c.JSON(ctx, "POST", "/api/cron/", map[string]any{
		"identifier": "restart_server", "params": map[string]string{"server_id": server.ID},
		"name": "restart-" + server.ID, "cron": "0 8 1 1 *",
	}, &independent, 200); err != nil {
		return err
	}
	var managedID string
	if err = t.Step("concurrent server requests create one managed plan without adopting an independent display-name match", func() error {
		type result struct {
			job scheduleIdentity
			err error
		}
		results := make(chan result, 2)
		start := make(chan struct{})
		for range 2 {
			go func() {
				<-start
				var job scheduleIdentity
				err := c.JSON(ctx, "POST", base+"/restart-schedule", map[string]string{"custom_cron": "0 6 1 1 *"}, &job, 200)
				results <- result{job, err}
			}()
		}
		close(start)
		var requestError error
		for range 2 {
			outcome := <-results
			if outcome.err != nil {
				requestError = outcome.err
				continue
			}
			if managedID != "" && managedID != outcome.job.ID {
				requestError = fmt.Errorf("concurrent managed creation returned different IDs: %s and %s", managedID, outcome.job.ID)
			}
			managedID = outcome.job.ID
		}
		if requestError != nil {
			return requestError
		}
		var inventory []scheduleIdentity
		if err := c.JSON(ctx, "GET", "/api/cron/?identifier=restart_server", nil, &inventory, 200); err != nil {
			return err
		}
		if managedID == "" || managedID == independent.ID || len(inventory) != 2 {
			return fmt.Errorf("managed creation duplicated or adopted another plan: %+v", inventory)
		}
		return nil
	}); err != nil {
		return err
	}
	name := "任意显示名称，与目标名称不同"
	update := func(cron, second string) error {
		return c.JSON(ctx, "PUT", "/api/cron/"+managedID, map[string]any{
			"identifier": "restart_server", "params": map[string]string{"server_id": server.ID},
			"name": name, "cron": cron, "second": second,
		}, nil, 200)
	}
	checkManaged := func(status, cron, registration string) error {
		actual, err := readScheduleIdentity(ctx, c, managedID)
		if err == nil && (actual.Name != name || actual.Identifier != "restart_server" || actual.Params.ServerID != server.ID || actual.Purpose == nil || *actual.Purpose != "restart" || actual.Status != status || actual.Cron != cron || actual.Registration != registration || actual.RegistrationError != nil) {
			return fmt.Errorf("managed plan lost its logical target, display name or desired state: %+v", actual)
		}
		return err
	}
	checkIndependent := func(status string) error {
		actual, err := readScheduleIdentity(ctx, c, independent.ID)
		if err == nil && (actual.Status != status || actual.Cron != "0 8 1 1 *" || actual.Name != "restart-"+server.ID || actual.Params.ServerID != server.ID || actual.Purpose != nil) {
			return fmt.Errorf("independent job was adopted or altered through its display name: %+v", actual)
		}
		return err
	}
	if err = update("0 6 1 1 *", "0"); err != nil {
		return err
	}
	if err = t.Step("managed mutations and backend restart preserve arbitrary display names and independent jobs", func() error {
		for _, stage := range []struct{ action, status, registration string }{{"pause", "paused", "inactive"}, {"resume", "active", "registered"}} {
			if err := c.JSON(ctx, "POST", base+"/restart-schedule/"+stage.action, nil, nil, 200); err != nil {
				return err
			}
			if err := checkManaged(stage.status, "0 6 1 1 *", stage.registration); err != nil {
				return err
			}
			if err := checkIndependent("active"); err != nil {
				return err
			}
		}
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		if err := checkManaged("active", "0 6 1 1 *", "registered"); err != nil {
			return err
		}
		return checkIndependent("active")
	}); err != nil {
		return err
	}
	var missingExecution scheduleExecution
	if err = t.Step("removal cancels active plans and explicit resume records a real missing-target skip", func() error {
		var removed struct {
			IDs []string `json:"cancelled_restart_cronjob_ids"`
		}
		if err := c.RunTask(ctx, "POST", base+"/operations", map[string]string{"action": "remove"}, &removed); err != nil {
			return err
		}
		slices.Sort(removed.IDs)
		wanted := []string{managedID, independent.ID}
		slices.Sort(wanted)
		if !slices.Equal(removed.IDs, wanted) {
			return fmt.Errorf("removal did not cancel both exact-target active plans: %v", removed.IDs)
		}
		if err := checkManaged("cancelled", "0 6 1 1 *", "inactive"); err != nil {
			return err
		}
		if err := checkIndependent("cancelled"); err != nil {
			return err
		}
		if err := update("* * * * *", "*/2"); err != nil {
			return err
		}
		if err := checkManaged("cancelled", "* * * * *", "inactive"); err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", "/api/cron/"+managedID+"/resume", nil, nil, 200); err != nil {
			return err
		}
		missingExecution, err = waitScheduleSkip(ctx, c, managedID, "未登记", nil)
		if err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", "/api/cron/"+managedID+"/pause", nil, nil, 200); err != nil {
			return err
		}
		return c.JSON(ctx, "GET", base, nil, nil, 404)
	}); err != nil {
		return err
	}
	previous, err := scheduleHistory(ctx, c, managedID)
	if err != nil {
		return err
	}
	var stoppedExecution scheduleExecution
	if err = t.Step("same-name recreation retains a paused plan and the next explicit execution resolves the current stopped instance", func() error {
		if err := c.RunTask(ctx, "POST", base, map[string]string{"yaml_content": server.Compose}, nil); err != nil {
			return err
		}
		var current struct {
			Generation int `json:"server_generation"`
		}
		if err := c.JSON(ctx, "GET", base, nil, &current, 200); err != nil {
			return err
		}
		if current.Generation <= incarnation.Generation {
			return fmt.Errorf("same-name server was not recreated as a new instance: %+v", current)
		}
		if err := checkManaged("paused", "* * * * *", "inactive"); err != nil {
			return err
		}
		var selected scheduleIdentity
		if err := c.JSON(ctx, "GET", base+"/restart-schedule", nil, &selected, 200); err != nil {
			return err
		}
		if selected.ID != managedID || selected.Status != "paused" || selected.Name != name {
			return fmt.Errorf("recreation discarded or implicitly resumed the retained plan: %+v", selected)
		}
		if err := c.JSON(ctx, "POST", base+"/restart-schedule/resume", nil, nil, 200); err != nil {
			return err
		}
		stoppedExecution, err = waitScheduleSkip(ctx, c, managedID, "未在运行中", previous)
		if err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", base+"/restart-schedule/pause", nil, nil, 200); err != nil {
			return err
		}
		return fixtures.Status(ctx, c, server.ID, "exists")
	}); err != nil {
		return err
	}
	return t.Step("restart retains both skip histories and independent plans can be explicitly re-enabled", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		if err := checkManaged("paused", "* * * * *", "inactive"); err != nil {
			return err
		}
		rows, err := scheduleHistory(ctx, c, managedID)
		if err != nil {
			return err
		}
		for _, expected := range []scheduleExecution{missingExecution, stoppedExecution} {
			found := false
			for _, row := range rows {
				if row.ID == expected.ID && row.Status == expected.Status && slices.Equal(row.Messages, expected.Messages) {
					found = true
				}
			}
			if !found {
				return fmt.Errorf("restart lost retained scheduled execution: %+v", expected)
			}
		}
		if err := checkIndependent("cancelled"); err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", "/api/cron/"+independent.ID+"/resume", nil, nil, 200); err != nil {
			return err
		}
		return checkIndependent("active")
	})
}
