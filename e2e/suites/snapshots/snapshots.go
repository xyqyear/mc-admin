package snapshots

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "snapshots.restore-and-protection", Suite: "snapshots", Tags: []string{"smoke", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: restore},
		{ID: "snapshots.repository-and-selection", Suite: "snapshots", Tags: []string{"regression", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: repository},
		{ID: "snapshots.notes-and-multiple-paths", Suite: "snapshots", Tags: []string{"regression", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: notesAndMultiplePaths},
		{ID: "snapshots.mixed-ignored-targets", Suite: "snapshots", Tags: []string{"regression", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: mixedIgnoredTargets},
		{ID: "snapshots.logical-exclusions-and-shared-rules", Suite: "snapshots", Tags: []string{"regression", "restic"}, Recipe: recipes.Backup, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: logicalExclusions},
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
	for _, file := range []struct{ name, content string }{{"value.txt", "before"}, {"keep.txt", "protected before"}, {"empty.txt", ""}} {
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
	if err = t.Step("shared logical rules are read without creating history and submissions protect excluded files", func() error {
		var rules targetRules
		if err := client.JSON(ctx, "GET", "/api/snapshots/targets/rules?server_id="+id, nil, &rules, 200); err != nil {
			return err
		}
		if !slices.Equal(rules.Paths, []string{".mcmap", "restore/keep.txt"}) {
			return fmt.Errorf("shared logical exclusions differ: %+v", rules)
		}
		if err := client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"restore/keep.txt"}}}, nil, 400); err != nil {
			return err
		}
		var history struct {
			Total int `json:"total"`
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/restorations?server_id="+id, nil, &history, 200); err != nil {
			return err
		}
		if history.Total != 0 {
			return fmt.Errorf("reading rules or refusing an excluded target created restoration history")
		}
		return nil
	}); err != nil {
		return err
	}
	var created struct {
		Snapshot struct {
			ID string `json:"id"`
		} `json:"snapshot"`
	}
	if err = t.Step("real Restic snapshot is persisted and listed", func() error {
		if err := client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"restore"}}}, &created); err != nil {
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
	if err = client.RunTask(ctx, "DELETE", "/api/servers/"+id+"/files?path=/restore/empty.txt", nil, nil); err != nil {
		return err
	}
	request := map[string]any{"source_snapshot_id": created.Snapshot.ID, "scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"restore"}}}
	var previewID string
	if err = t.Step("preview reports changes without applying them", func() error {
		var preview struct {
			Actions []map[string]any `json:"actions"`
			Next    *int             `json:"next_cursor"`
		}
		result, err := client.RunTaskResult(ctx, "POST", "/api/snapshots/previews", request)
		if err != nil {
			return err
		}
		previewID, _ = result["preview_id"].(string)
		if previewID == "" {
			return fmt.Errorf("preview task returned no identity")
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/previews/"+previewID, nil, nil, 200); err != nil {
			return err
		}
		foundEmpty := false
		for cursor := 0; ; {
			if err := client.JSON(ctx, "GET", fmt.Sprintf("/api/snapshots/previews/%s/actions?limit=1&cursor=%d", previewID, cursor), nil, &preview, 200); err != nil {
				return err
			}
			if len(preview.Actions) != 1 {
				return fmt.Errorf("restore preview must return one change per requested page")
			}
			item, _ := preview.Actions[0]["item"].(string)
			if strings.HasSuffix(item, "/empty.txt") && preview.Actions[0]["action"] == "restored" {
				foundEmpty = true
			}
			if preview.Next == nil {
				break
			}
			if *preview.Next <= cursor {
				return fmt.Errorf("restore preview pagination did not advance")
			}
			cursor = *preview.Next
		}
		if !foundEmpty {
			return fmt.Errorf("restore preview omitted restoration of an empty file")
		}
		return fixtures.CheckFile(ctx, client, id, "/restore/value.txt", "after")
	}); err != nil {
		return err
	}
	if err = t.Step("changed preview refuses writes until prepared again", func() error {
		if err := fixtures.WriteFile(ctx, client, id, "/restore/value.txt", "edit after preview"); err != nil {
			return err
		}
		stale := map[string]any{"scope": request["scope"], "source_snapshot_id": created.Snapshot.ID, "preview_id": previewID}
		if err := client.JSON(ctx, "POST", "/api/snapshots/restorations", stale, nil, 409); err != nil {
			return err
		}
		if err := fixtures.CheckFile(ctx, client, id, "/restore/value.txt", "edit after preview"); err != nil {
			return err
		}
		if err := fixtures.WriteFile(ctx, client, id, "/restore/value.txt", "after"); err != nil {
			return err
		}
		result, err := client.RunTaskResult(ctx, "POST", "/api/snapshots/previews", request)
		if err != nil {
			return err
		}
		previewID, _ = result["preview_id"].(string)
		return nil
	}); err != nil {
		return err
	}

	var restorationID string
	if err = t.Step("background restore restores content, deletes extra files and protects ignored data", func() error {
		event, err := client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations", map[string]any{"scope": map[string]any{"kind": "paths", "server_id": id, "paths": []string{"restore"}}, "source_snapshot_id": created.Snapshot.ID, "preview_id": previewID, "entry_point": "files"})
		if err != nil {
			return err
		}
		if event["safety_snapshot_id"] == nil || event["safety_snapshot_id"] == "" {
			return fmt.Errorf("restore did not report a safety snapshot")
		}
		restorationID, _ = event["restoration_id"].(string)
		if restorationID == "" {
			return fmt.Errorf("restore did not retain its history ID")
		}
		if err = fixtures.CheckFile(ctx, client, id, "/restore/value.txt", "before"); err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, client, id, "/restore/keep.txt", "protected after"); err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, client, id, "/restore/empty.txt", ""); err != nil {
			return err
		}
		empty, err := os.Stat(filepath.Join(t.Env.Dir, "servers", id, "data", "restore", "empty.txt"))
		if err != nil {
			return err
		}
		if !empty.Mode().IsRegular() || empty.Size() != 0 {
			return fmt.Errorf("restored empty file is not a regular zero-byte file")
		}
		return client.JSON(ctx, "GET", "/api/servers/"+id+"/files/content?path=/restore/extra.txt", nil, nil, 404)
	}); err != nil {
		return err
	}
	if err = client.RunTask(ctx, "DELETE", "/api/snapshots/previews/"+previewID, nil, nil); err != nil {
		return err
	}

	return t.Step("history rollback replaces later edits and is itself reversible", func() error {
		var history struct {
			Total int `json:"total"`
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/restorations?server_id="+id+"&kind=paths&status=succeeded&entry_point=files", nil, &history, 200); err != nil {
			return err
		}
		if history.Total != 1 {
			return fmt.Errorf("restore did not create exactly one history record")
		}
		var active struct {
			Total int `json:"total"`
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/restorations/active?server_id="+id+"&limit=1", nil, &active, 200); err != nil {
			return err
		}
		if active.Total != 0 {
			return fmt.Errorf("completed restoration remains active")
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/restorations?server_id="+id+"&kind=world&status=failed", nil, &history, 200); err != nil {
			return err
		}
		if history.Total != 0 {
			return fmt.Errorf("restoration filters included an unrelated result")
		}
		var record struct {
			ID        string `json:"id"`
			Status    string `json:"status"`
			Available bool   `json:"rollback_available"`
			Targets   []struct {
				ServerID   string `json:"server_id"`
				Generation int    `json:"generation"`
			} `json:"targets"`
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/restorations/"+restorationID, nil, &record, 200); err != nil {
			return err
		}
		if len(record.Targets) != 1 || record.Targets[0].ServerID != id || record.Targets[0].Generation < 1 {
			return fmt.Errorf("restoration lost its target generation")
		}
		if record.ID != restorationID || record.Status != "succeeded" || !record.Available {
			return fmt.Errorf("completed restore has inconsistent history")
		}
		if err := fixtures.WriteFile(ctx, client, id, "/restore/value.txt", "edited after restore"); err != nil {
			return err
		}
		rollback, err := client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations/"+restorationID+"/rollback", nil)
		if err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, client, id, "/restore/value.txt", "after"); err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, client, id, "/restore/extra.txt", "remove on restore"); err != nil {
			return err
		}
		if err = client.JSON(ctx, "GET", "/api/servers/"+id+"/files/content?path=/restore/empty.txt", nil, nil, 404); err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, client, id, "/restore/keep.txt", "protected after"); err != nil {
			return err
		}
		rollbackID, ok := rollback["restoration_id"].(string)
		if !ok || rollbackID == restorationID {
			return fmt.Errorf("rollback must create a distinct history record")
		}
		if err = client.RunTask(ctx, "POST", "/api/snapshots/restorations/"+rollbackID+"/rollback", nil, nil); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/restore/value.txt", "edited after restore")
	})
}
