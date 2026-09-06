package snapshots

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func updateConfig(ctx context.Context, client *api.Client, mutate func(map[string]any)) error {
	var config struct {
		Data map[string]any `json:"config_data"`
	}
	if err := client.JSON(ctx, "GET", "/api/config/modules/snapshots", nil, &config, 200); err != nil {
		return err
	}
	mutate(config.Data)
	return client.JSON(ctx, "PUT", "/api/config/modules/snapshots", map[string]any{"config_data": config.Data}, nil, 200)
}

func repository(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	var usage struct {
		Used      float64 `json:"backupUsedGB"`
		Total     float64 `json:"backupTotalGB"`
		Available float64 `json:"backupAvailableGB"`
	}
	if err = client.JSON(ctx, "GET", "/api/snapshots/repository-usage", nil, &usage, 200); err != nil {
		return err
	}
	if usage.Total <= 0 || usage.Used < 0 || usage.Available <= 0 || usage.Available > usage.Total {
		return fmt.Errorf("invalid repository filesystem usage: %+v", usage)
	}
	var locks struct {
		Locks string `json:"locks"`
	}
	if err = client.JSON(ctx, "GET", "/api/snapshots/locks", nil, &locks, 200); err != nil {
		return err
	}
	var unlocked struct {
		Message string `json:"message"`
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots/unlock", nil, &unlocked, 200); err != nil {
		return err
	}
	if unlocked.Message != "Repository unlocked successfully" {
		return fmt.Errorf("unlock did not complete")
	}
	for _, directory := range []string{"alpha", "beta", "world"} {
		if err = client.JSON(ctx, "POST", "/api/servers/"+id+"/files/create", map[string]string{"type": "directory", "path": "/", "name": directory}, nil, 200); err != nil {
			return err
		}
	}
	for _, file := range []string{"alpha/one.txt", "beta/two.txt", "world/protected.txt"} {
		if err = fixtures.CreateFile(ctx, client, id, "/"+file, file); err != nil {
			return err
		}
	}
	if err = fixtures.CreateFile(ctx, client, id, "/server.properties", "level-name=world\n"); err != nil {
		return err
	}
	if err = updateConfig(ctx, client, func(config map[string]any) {
		config["ignored_paths"] = []string{".mcmap", "<LEVEL_NAME>/protected.txt"}
	}); err != nil {
		return err
	}
	for _, input := range []map[string]any{{"paths": []string{"/alpha"}}, {"server_id": id, "paths": []string{"/../../outside"}}, {"server_id": id, "paths": []string{"/world/protected.txt"}}} {
		if err = client.JSON(ctx, "POST", "/api/snapshots", input, nil, 400); err != nil {
			return err
		}
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"server_id": id, "paths": []string{"/missing"}}, nil, 404); err != nil {
		return err
	}
	data := filepath.Join(t.Env.Dir, "servers", id, "data")
	if err = os.Symlink(t.Env.Dir, filepath.Join(data, "escape")); err != nil {
		return err
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"server_id": id, "paths": []string{"/escape"}}, nil, 400); err != nil {
		return err
	}
	if err = os.Remove(filepath.Join(data, "escape")); err != nil {
		return err
	}
	ids := []string{}
	for _, input := range []map[string]any{{"server_id": id, "paths": []string{"/alpha", "/beta"}}, {"server_id": id}, {}} {
		var response struct {
			Snapshot struct {
				ID    string   `json:"id"`
				Paths []string `json:"paths"`
			} `json:"snapshot"`
		}
		if err = client.JSON(ctx, "POST", "/api/snapshots", input, &response, 200); err != nil {
			return err
		}
		if response.Snapshot.ID == "" || len(response.Snapshot.Paths) == 0 {
			return fmt.Errorf("snapshot returned no identity or coverage")
		}
		ids = append(ids, response.Snapshot.ID)
	}
	for _, suffix := range []string{"", "?server_id=" + id, "?server_id=" + id + "&path=" + url.QueryEscape("/alpha")} {
		var listed struct {
			Snapshots []struct {
				ID string `json:"id"`
			} `json:"snapshots"`
		}
		if err = client.JSON(ctx, "GET", "/api/snapshots"+suffix, nil, &listed, 200); err != nil {
			return err
		}
		expected := 3
		if suffix == "?server_id="+id {
			expected = 2
		}
		if len(listed.Snapshots) != expected {
			return fmt.Errorf("snapshot coverage listing %q returned %d, expected %d", suffix, len(listed.Snapshots), expected)
		}
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots/restore/preview", map[string]any{"snapshot_id": ids[2], "server_id": id, "paths": []string{"/world/protected.txt"}}, nil, 400); err != nil {
		return err
	}
	for _, snapshot := range ids {
		if err = client.JSON(ctx, "DELETE", "/api/snapshots/"+snapshot, nil, nil, 200); err != nil {
			return err
		}
	}
	var listed struct {
		Snapshots []any `json:"snapshots"`
	}
	if err = client.JSON(ctx, "GET", "/api/snapshots", nil, &listed, 200); err != nil {
		return err
	}
	if len(listed.Snapshots) != 0 {
		return fmt.Errorf("forget/prune left snapshots behind")
	}
	return nil
}

func timeRestriction(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	var cron struct {
		ID string `json:"cronjob_id"`
	}
	if err = client.JSON(ctx, "POST", "/api/cron/", map[string]any{"identifier": "backup", "name": "E2E backup restriction", "cron": "* * * * *", "params": map[string]any{"server_id": id, "enable_forget": false}}, &cron, 200); err != nil {
		return err
	}
	if cron.ID == "" {
		return fmt.Errorf("backup schedule returned no job ID")
	}
	if err = client.JSON(ctx, "POST", "/api/cron/"+cron.ID+"/pause", nil, nil, 200); err != nil {
		return err
	}
	if err = updateConfig(ctx, client, func(config map[string]any) {
		config["time_restriction"] = map[string]any{"enabled": true, "before_seconds": 300, "after_seconds": 300}
	}); err != nil {
		return err
	}
	var rejected struct {
		Detail string `json:"detail"`
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"server_id": id}, &rejected, 400); err != nil {
		return err
	}
	if !strings.Contains(rejected.Detail, "备份时间") {
		return fmt.Errorf("snapshot rejected for unrelated reason: %q", rejected.Detail)
	}
	if err = updateConfig(ctx, client, func(config map[string]any) { config["time_restriction"].(map[string]any)["enabled"] = false }); err != nil {
		return err
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"server_id": id}, nil, 200); err != nil {
		return err
	}
	if err = client.JSON(ctx, "DELETE", "/api/cron/"+cron.ID, nil, nil, 200); err != nil {
		return err
	}
	return nil
}

func staleLock(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	if _, err = backend.Docker.Run(ctx, "exec", "--detach", backend.Name, "sh", "-c", `sleep 120 | restic --repo /data/restic --insecure-no-password backup --stdin --stdin-filename e2e-lock > /data/e2e-lock.log 2>&1 & echo $! > /data/e2e-lock.pid; wait`); err != nil {
		return err
	}
	var locks struct {
		Locks string `json:"locks"`
	}
	if err = api.Wait(ctx, 100*time.Millisecond, "real Restic process holds repository lock", func(ctx context.Context) (bool, error) {
		if err := client.JSON(ctx, "GET", "/api/snapshots/locks", nil, &locks, 200); err != nil {
			return false, api.Permanent(err)
		}
		return strings.TrimSpace(locks.Locks) != "", nil
	}); err != nil {
		return err
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots/unlock", nil, nil, 200); err != nil {
		return err
	}
	if err = client.JSON(ctx, "GET", "/api/snapshots/locks", nil, &locks, 200); err != nil {
		return err
	}
	if strings.TrimSpace(locks.Locks) == "" {
		return fmt.Errorf("unlock removed an active lock")
	}
	pidText, err := backend.Docker.Run(ctx, "exec", backend.Name, "cat", "/data/e2e-lock.pid")
	if err != nil {
		return err
	}
	pid, err := strconv.Atoi(strings.TrimSpace(pidText))
	if err != nil || pid <= 1 {
		return fmt.Errorf("invalid owned Restic PID %q", pidText)
	}
	command, err := backend.Docker.Run(ctx, "exec", backend.Name, "cat", fmt.Sprintf("/proc/%d/cmdline", pid))
	if err != nil {
		return err
	}
	if !strings.Contains(command, "restic\x00--repo\x00/data/restic") || !strings.Contains(command, "e2e-lock") {
		return fmt.Errorf("refusing to terminate process without expected owned Restic command")
	}
	if _, err = backend.Docker.Run(ctx, "exec", backend.Name, "sh", "-c", `kill -KILL "$1"`, "--", strconv.Itoa(pid)); err != nil {
		return err
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots/unlock", nil, nil, 200); err != nil {
		return err
	}
	if err = client.JSON(ctx, "GET", "/api/snapshots/locks", nil, &locks, 200); err != nil {
		return err
	}
	if strings.TrimSpace(locks.Locks) != "" {
		return fmt.Errorf("stale lock remained after unlock: %q", locks.Locks)
	}
	return client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"server_id": fixtures.ServerOf(t.Env).ID}, nil, 200)
}
