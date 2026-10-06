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

func checkSnapshotIDs(actual, expected []string) error {
	if len(actual) != len(expected) {
		return fmt.Errorf("snapshot listing returned %d identities, expected %d", len(actual), len(expected))
	}
	wanted := make(map[string]bool, len(expected))
	for _, id := range expected {
		wanted[id] = true
	}
	for _, id := range actual {
		if !wanted[id] {
			return fmt.Errorf("snapshot listing returned unexpected or duplicate ID %q", id)
		}
		delete(wanted, id)
	}
	return nil
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
	if err = client.JSON(ctx, "GET", "/api/snapshots/usage", nil, &usage, 200); err != nil {
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
	if err = client.RunTask(ctx, "POST", "/api/snapshots/unlock", nil, &unlocked); err != nil {
		return err
	}
	if !strings.Contains(unlocked.Message, "失效的仓库锁已清理") {
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
	for index, input := range []map[string]any{map[string]any{"scope": map[string]any{"kind": "paths", "paths": []string{"alpha"}}}, map[string]any{"scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"../../outside"}}}, map[string]any{"scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"world/protected.txt"}}}} {
		if err = client.JSON(ctx, "POST", "/api/snapshots", input, nil, []int{422, 422, 400}[index]); err != nil {
			return err
		}
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"missing"}}}, nil, 404); err != nil {
		return err
	}
	data := filepath.Join(t.Env.Dir, "servers", id, "data")
	if err = os.Symlink(t.Env.Dir, filepath.Join(data, "escape")); err != nil {
		return err
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"escape"}}}, nil, 400); err != nil {
		return err
	}
	if err = os.Remove(filepath.Join(data, "escape")); err != nil {
		return err
	}
	ids := []string{}
	for _, input := range []map[string]any{map[string]any{"scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"alpha", "beta"}}}, map[string]any{"scope": map[string]any{"kind": "server", "server_id": id}}, map[string]any{"scope": map[string]any{"kind": "global"}}} {
		var response struct {
			Snapshot struct {
				ID    string   `json:"id"`
				Paths []string `json:"paths"`
			} `json:"snapshot"`
		}
		if err = client.RunTask(ctx, "POST", "/api/snapshots", input, &response); err != nil {
			return err
		}
		if response.Snapshot.ID == "" || len(response.Snapshot.Paths) == 0 {
			return fmt.Errorf("snapshot returned no identity or coverage")
		}
		ids = append(ids, response.Snapshot.ID)
	}
	pathSnapshotID, serverSnapshotID, globalSnapshotID := ids[0], ids[1], ids[2]
	for _, invalidID := range []string{"--keep-last=0", "latest", pathSnapshotID[:8]} {
		if err = client.JSON(ctx, "DELETE", "/api/snapshots/"+invalidID, nil, nil, 422); err != nil {
			return err
		}
	}
	for _, query := range []struct {
		suffix string
		ids    []string
	}{
		{"", ids},
		{"?server_id=" + id, []string{serverSnapshotID, globalSnapshotID}},
		{"?server_id=" + id + "&path=" + url.QueryEscape("/alpha"), ids},
	} {
		var listed struct {
			Snapshots []struct {
				ID string `json:"id"`
			} `json:"snapshots"`
		}
		if err = client.JSON(ctx, "GET", "/api/snapshots"+query.suffix, nil, &listed, 200); err != nil {
			return err
		}
		actual := make([]string, 0, len(listed.Snapshots))
		for _, snapshot := range listed.Snapshots {
			actual = append(actual, snapshot.ID)
		}
		if err = checkSnapshotIDs(actual, query.ids); err != nil {
			return fmt.Errorf("snapshot coverage listing %q: %w", query.suffix, err)
		}
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots/previews", map[string]any{"source_snapshot_id": globalSnapshotID, "scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"world/protected.txt"}}}, nil, 400); err != nil {
		return err
	}
	for _, snapshot := range ids {
		if err = client.RunTask(ctx, "DELETE", "/api/snapshots/"+snapshot, nil, nil); err != nil {
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
	if err = client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"scope": map[string]any{"kind": "server", "server_id": id}}, &rejected, 400); err != nil {
		return err
	}
	if !strings.Contains(rejected.Detail, "备份时间") {
		return fmt.Errorf("snapshot rejected for unrelated reason: %q", rejected.Detail)
	}
	if err = updateConfig(ctx, client, func(config map[string]any) { config["time_restriction"].(map[string]any)["enabled"] = false }); err != nil {
		return err
	}
	if err = client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": map[string]any{"kind": "server", "server_id": id}}, nil); err != nil {
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
	if err = client.RunTask(ctx, "POST", "/api/snapshots/unlock", nil, nil); err != nil {
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
	if err = client.RunTask(ctx, "POST", "/api/snapshots/unlock", nil, nil); err != nil {
		return err
	}
	if err = client.JSON(ctx, "GET", "/api/snapshots/locks", nil, &locks, 200); err != nil {
		return err
	}
	if strings.TrimSpace(locks.Locks) != "" {
		return fmt.Errorf("stale lock remained after unlock: %q", locks.Locks)
	}
	return client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": map[string]any{"kind": "server", "server_id": fixtures.ServerOf(t.Env).ID}}, nil)
}
