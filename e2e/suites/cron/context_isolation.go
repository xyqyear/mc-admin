package cron

import (
	"context"
	"fmt"
	"reflect"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type isolatedExecution struct {
	ID       string     `json:"execution_id"`
	Status   string     `json:"status"`
	Started  time.Time  `json:"started_at"`
	Ended    *time.Time `json:"ended_at"`
	Messages []string   `json:"messages"`
}

type isolatedOperation struct {
	ID             string     `json:"operation_id"`
	LegacyID       string     `json:"legacy_id"`
	Kind           string     `json:"kind"`
	Origin         string     `json:"origin"`
	State          string     `json:"state"`
	Created        time.Time  `json:"created_at"`
	Ended          *time.Time `json:"ended_at"`
	WritersStopped bool       `json:"writers_stopped"`
}

func waitIsolatedExecution(ctx context.Context, c *api.Client, id, status string) (isolatedExecution, error) {
	var result isolatedExecution
	err := api.Wait(ctx, 200*time.Millisecond, "independent scheduled execution "+id, func(ctx context.Context) (bool, error) {
		var rows []isolatedExecution
		if err := c.JSON(ctx, "GET", "/api/cron/"+id+"/executions", nil, &rows, 200); err != nil {
			return false, api.Permanent(err)
		}
		if len(rows) == 0 {
			return false, nil
		}
		if len(rows) != 1 {
			return false, api.Permanent(fmt.Errorf("one scheduled occurrence produced %d execution rows for %s", len(rows), id))
		}
		result = rows[0]
		if result.Status == "running" {
			return false, nil
		}
		if result.Status != status || result.ID == "" || result.Ended == nil || result.Ended.Before(result.Started) || len(result.Messages) == 0 {
			return false, api.Permanent(fmt.Errorf("cron %s expected %s with terminal metadata, got %+v", id, status, result))
		}
		return true, nil
	})
	return result, err
}

func creationContextIsolation(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	if err = fixtures.Operation(ctx, c, server.ID, "remove"); err != nil {
		return err
	}
	var next struct {
		At time.Time `json:"next_run_time"`
	}
	if err = c.JSON(ctx, "GET", "/api/cron/system:self_check/next-run-time", nil, &next, 200); err != nil {
		return err
	}
	if next.At.IsZero() {
		return fmt.Errorf("system self-check omitted its schedule timezone")
	}
	first := time.Now().In(next.At.Location()).Add(20 * time.Second).Truncate(time.Second)
	plans := []struct {
		id, identifier, status, state string
		offset                        time.Duration
		params                        map[string]any
	}{
		{"e2e-context-failure", "backup", "failed", "failed", 0, map[string]any{"server_id": server.ID, "path": "missing-backup-input", "enable_forget": false}},
		{"e2e-context-success", "backup", "completed", "succeeded", 10 * time.Second, map[string]any{"server_id": server.ID, "enable_forget": false}},
		{"system:self_check", "self_check", "completed", "succeeded", 20 * time.Second, map[string]any{"scope": "global"}},
	}
	for _, plan := range plans {
		at := first.Add(plan.offset)
		body := map[string]any{
			"cronjob_id": plan.id, "identifier": plan.identifier, "params": plan.params,
			"cron":   fmt.Sprintf("%d %d %d %d *", at.Minute(), at.Hour(), at.Day(), at.Month()),
			"second": fmt.Sprint(at.Second()), "name": "E2E independent " + plan.id,
		}
		method, path := "POST", "/api/cron/"
		if plan.identifier == "self_check" {
			method, path = "PUT", "/api/cron/"+plan.id
		}
		if err = c.JSON(ctx, method, path, body, nil, 200); err != nil {
			return err
		}
		var scheduled struct {
			At time.Time `json:"next_run_time"`
		}
		if err = c.JSON(ctx, "GET", "/api/cron/"+plan.id+"/next-run-time", nil, &scheduled, 200); err != nil {
			return err
		}
		if !scheduled.At.Equal(at) {
			return fmt.Errorf("cron %s scheduled %s instead of owned occurrence %s", plan.id, scheduled.At, at)
		}
	}

	accepted, err := c.StartTask(ctx, "POST", "/api/servers/"+server.ID, map[string]any{
		"yaml_content": server.Compose, "restart_schedule": map[string]string{"custom_cron": "0 0 1 1 *"},
	})
	if err != nil {
		return err
	}
	created, err := c.Task(ctx, accepted.ID)
	if err != nil {
		return err
	}
	scheduleID, ok := created.Result["restart_cronjob_id"].(string)
	if !ok || scheduleID == "" || created.Result["server_id"] != server.ID {
		return fmt.Errorf("server creation did not retain its bundled restart schedule: %+v", created)
	}
	var restart job
	if err = c.JSON(ctx, "GET", "/api/cron/"+scheduleID, nil, &restart, 200); err != nil {
		return err
	}
	if restart.Identifier != "restart_server" || restart.Registration != "registered" {
		return fmt.Errorf("bundled restart schedule was not registered: %+v", restart)
	}
	var parent isolatedOperation
	if err = c.JSON(ctx, "GET", "/api/operations/"+accepted.ID, nil, &parent, 200); err != nil {
		return err
	}
	if parent.Kind != "server_create" || parent.Origin != "task" || parent.State != "succeeded" || parent.Ended == nil || !parent.WritersStopped || !parent.Ended.Before(first) {
		return fmt.Errorf("creation must finish before the independent scheduled occurrences: %+v", parent)
	}
	const filename = "/scheduled-content.txt"
	const content = "真实定时备份必须保留这些字节\n"
	if err = fixtures.CreateFile(ctx, c, server.ID, filename, content); err != nil {
		return err
	}
	if !time.Now().Before(first) {
		return fmt.Errorf("fixture preparation exceeded the scheduled occurrence deadline")
	}

	executions := make(map[string]isolatedExecution)
	operationIDs := map[string]bool{parent.ID: true}
	// Scheduler mutations after creation would replace the inherited wakeup context under test.
	for _, plan := range plans {
		if err = t.Step("scheduled "+plan.id+" owns its terminal operation after server creation", func() error {
			execution, err := waitIsolatedExecution(ctx, c, plan.id, plan.status)
			if err != nil {
				return err
			}
			if execution.Started.Before(*parent.Ended) {
				return fmt.Errorf("cron ran before its completed creation parent")
			}
			if plan.status == "failed" && !strings.Contains(strings.Join(execution.Messages, "\n"), "定时任务执行失败: 服务器内部错误，请稍后重试") {
				return fmt.Errorf("failed backup did not retain its safe public failure: %v", execution.Messages)
			}
			var operations []isolatedOperation
			if err = c.JSON(ctx, "GET", "/api/operations?limit=100", nil, &operations, 200); err != nil {
				return err
			}
			matches := 0
			for _, operation := range operations {
				if operation.Origin != "cron" || operation.LegacyID != execution.ID {
					continue
				}
				matches++
				if operation.ID == "" || operationIDs[operation.ID] || operation.Kind != "cron_"+plan.identifier || operation.State != plan.state || operation.Ended == nil || !operation.WritersStopped || operation.Created.Before(*parent.Ended) {
					return fmt.Errorf("cron execution reused another operation or lost its independent terminal state: %+v", operation)
				}
				operationIDs[operation.ID] = true
			}
			if matches != 1 {
				return fmt.Errorf("cron execution %s has %d independent journal records", execution.ID, matches)
			}
			executions[plan.id] = execution
			return nil
		}); err != nil {
			return err
		}
	}
	if err = t.Step("scheduled self-check retains real findings linked from its execution", func() error {
		var history struct {
			Runs []struct {
				ID       string    `json:"id"`
				Trigger  string    `json:"trigger"`
				Scope    string    `json:"scope"`
				Started  time.Time `json:"started_at"`
				Finished time.Time `json:"finished_at"`
			} `json:"runs"`
		}
		if err := c.JSON(ctx, "GET", "/api/self-check/runs?limit=100", nil, &history, 200); err != nil {
			return err
		}
		found := 0
		for _, run := range history.Runs {
			if run.Trigger != "scheduled" || run.Started.Before(*parent.Ended) {
				continue
			}
			found++
			if run.ID == "" || run.Scope != "full" || run.Finished.Before(run.Started) || !strings.Contains(strings.Join(executions["system:self_check"].Messages, "\n"), run.ID) {
				return fmt.Errorf("cron self-check lost its persisted result identity: %+v", run)
			}
			var detail struct {
				Findings []struct {
					Check  string `json:"check_id"`
					Status string `json:"status"`
				} `json:"findings"`
			}
			if err := c.JSON(ctx, "GET", "/api/self-check/runs/"+run.ID, nil, &detail, 200); err != nil {
				return err
			}
			checks := map[string]string{}
			for _, finding := range detail.Findings {
				checks[finding.Check] = finding.Status
			}
			for _, check := range []string{"backup.restic_reachable", "server.filesystem_db_sync"} {
				if checks[check] != "passed" {
					return fmt.Errorf("scheduled self-check omitted real healthy finding %s: %v", check, checks)
				}
			}
		}
		if found != 1 {
			return fmt.Errorf("expected one scheduled self-check result, got %d", found)
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("only the successful backup produces a restorable real snapshot", func() error {
		var snapshots struct {
			Snapshots []struct {
				ID string `json:"id"`
			} `json:"snapshots"`
		}
		if err := c.JSON(ctx, "GET", "/api/snapshots", nil, &snapshots, 200); err != nil {
			return err
		}
		if len(snapshots.Snapshots) != 1 || len(snapshots.Snapshots[0].ID) != 64 {
			return fmt.Errorf("one successful and one failed cron backup produced unexpected snapshots: %+v", snapshots)
		}
		if err := fixtures.WriteFile(ctx, c, server.ID, filename, "changed after scheduled backup"); err != nil {
			return err
		}
		if err := c.RunTask(ctx, "POST", "/api/snapshots/restorations", map[string]any{
			"source_snapshot_id": snapshots.Snapshots[0].ID,
			"scope":              map[string]any{"kind": "paths", "server_id": server.ID, "paths": []string{strings.TrimPrefix(filename, "/")}},
		}, nil); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, c, server.ID, filename, content)
	}); err != nil {
		return err
	}
	var unchanged isolatedOperation
	if err = c.JSON(ctx, "GET", "/api/operations/"+parent.ID, nil, &unchanged, 200); err != nil {
		return err
	}
	if !reflect.DeepEqual(parent, unchanged) {
		return fmt.Errorf("independent scheduled jobs rewrote their completed creation parent: before=%+v after=%+v", parent, unchanged)
	}
	return nil
}
