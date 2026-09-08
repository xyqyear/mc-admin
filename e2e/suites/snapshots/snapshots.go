package snapshots

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "snapshots.restore-and-protection", Suite: "snapshots", Tags: []string{"smoke", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: restore},
		{ID: "snapshots.repository-and-selection", Suite: "snapshots", Tags: []string{"regression", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: repository},
		{ID: "snapshots.backup-time-restriction", Suite: "snapshots", Tags: []string{"regression", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: timeRestriction},
		{ID: "snapshots.stale-lock-recovery", Suite: "snapshots", Tags: []string{"regression", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: staleLock},
	}
}

func restore(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	if err = client.JSON(ctx, "POST", "/api/servers/"+id+"/files/create", map[string]string{"name": "restore", "path": "/", "type": "directory"}, nil, 200); err != nil {
		return err
	}
	for _, file := range []struct{ name, content string }{{"value.txt", "before"}, {"keep.txt", "protected before"}} {
		if err = fixtures.CreateFile(ctx, client, id, "/restore/"+file.name, file.content); err != nil {
			return err
		}
	}
	var config struct {
		Data map[string]any `json:"config_data"`
	}
	if err = client.JSON(ctx, "GET", "/api/config/modules/snapshots", nil, &config, 200); err != nil {
		return err
	}
	config.Data["ignored_paths"] = []string{".mcmap", "restore/keep.txt"}
	if err = client.JSON(ctx, "PUT", "/api/config/modules/snapshots", map[string]any{"config_data": config.Data}, nil, 200); err != nil {
		return err
	}
	var created struct {
		Snapshot struct {
			ID string `json:"id"`
		} `json:"snapshot"`
	}
	if err = t.Step("real Restic snapshot is persisted and listed", func() error {
		if err := client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"server_id": id, "paths": []string{"/restore"}}, &created, 200); err != nil {
			return err
		}
		if created.Snapshot.ID == "" {
			return fmt.Errorf("snapshot has no ID")
		}
		var listed struct {
			Snapshots []struct {
				ID string `json:"id"`
			} `json:"snapshots"`
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots?server_id="+id+"&path=/restore", nil, &listed, 200); err != nil {
			return err
		}
		if len(listed.Snapshots) != 1 || listed.Snapshots[0].ID != created.Snapshot.ID {
			return fmt.Errorf("snapshot missing from listing")
		}
		return nil
	}); err != nil {
		return err
	}
	if err = fixtures.WriteFile(ctx, client, id, "/restore/value.txt", "after"); err != nil {
		return err
	}
	if err = fixtures.WriteFile(ctx, client, id, "/restore/keep.txt", "protected after"); err != nil {
		return err
	}
	if err = fixtures.CreateFile(ctx, client, id, "/restore/extra.txt", "remove on restore"); err != nil {
		return err
	}
	request := map[string]any{"snapshot_id": created.Snapshot.ID, "server_id": id, "paths": []string{"/restore"}}
	if err = t.Step("preview reports changes without applying them", func() error {
		var preview struct {
			Actions []map[string]any `json:"actions"`
		}
		if err := client.JSON(ctx, "POST", "/api/snapshots/restore/preview", request, &preview, 200); err != nil {
			return err
		}
		if len(preview.Actions) == 0 {
			return fmt.Errorf("restore preview contains no actions")
		}
		return fixtures.CheckFile(ctx, client, id, "/restore/value.txt", "after")
	}); err != nil {
		return err
	}
	return t.Step("streamed restore restores content, deletes extra files and protects ignored data", func() error {
		event, err := client.SSE(ctx, "POST", "/api/snapshots/restore", request, "complete")
		if err != nil {
			return err
		}
		if event["safety_snapshot_id"] == nil || event["safety_snapshot_id"] == "" {
			return fmt.Errorf("restore did not report a safety snapshot")
		}
		if err = fixtures.CheckFile(ctx, client, id, "/restore/value.txt", "before"); err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, client, id, "/restore/keep.txt", "protected after"); err != nil {
			return err
		}
		return client.JSON(ctx, "GET", "/api/servers/"+id+"/files/content?path=/restore/extra.txt", nil, nil, 404)
	})
}
