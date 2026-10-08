package snapshots

import (
	"context"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type restoreSource struct {
	ID           string   `json:"id"`
	Paths        []string `json:"paths"`
	SkippedPaths []string `json:"skipped_paths"`
	SkippedCount int      `json:"skipped_count"`
}

func mixedIgnoredTargets(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	for _, file := range []struct{ name, content string }{{"allowed.txt", "source"}, {"protected.txt", "protected source"}} {
		if err = fixtures.CreateFile(ctx, client, id, "/"+file.name, file.content); err != nil {
			return err
		}
	}
	if err = updateConfig(ctx, client, func(config map[string]any) { config["ignored_paths"] = []string{".mcmap", "protected.txt"} }); err != nil {
		return err
	}
	scope := map[string]any{"kind": "paths", "server_id": id, "paths": []string{"allowed.txt", "protected.txt"}}
	var partial, historical struct {
		Snapshot restoreSource `json:"snapshot"`
		Skipped  []string      `json:"skipped_paths"`
	}
	if err = client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": scope}, &partial); err != nil {
		return err
	}
	if len(partial.Snapshot.Paths) != 1 || !strings.HasSuffix(partial.Snapshot.Paths[0], "/allowed.txt") || len(partial.Skipped) != 1 || !strings.HasSuffix(partial.Skipped[0], "/protected.txt") {
		return fmt.Errorf("mixed creation did not skip exactly the protected root: %+v", partial)
	}
	if err = client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": map[string]any{"kind": "server", "server_id": id}}, &historical); err != nil {
		return err
	}
	if err = t.Step("all ignored selections reject before creating restoration history", func() error {
		protected := map[string]any{"kind": "paths", "server_id": id, "paths": []string{"protected.txt"}}
		for _, endpoint := range []string{"/api/snapshots", "/api/snapshots/previews", "/api/snapshots/restorations"} {
			body := map[string]any{"scope": protected}
			if endpoint != "/api/snapshots" {
				body["source_snapshot_id"] = historical.Snapshot.ID
			}
			if err := client.JSON(ctx, "POST", endpoint, body, nil, 400); err != nil {
				return err
			}
		}
		var history struct {
			Total int `json:"total"`
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/restorations?server_id="+id, nil, &history, 200); err != nil {
			return err
		}
		if history.Total != 0 {
			return fmt.Errorf("rejected all-ignored selection created history")
		}
		return nil
	}); err != nil {
		return err
	}
	if err = updateConfig(ctx, client, func(config map[string]any) { config["ignored_paths"] = []string{".mcmap"} }); err != nil {
		return err
	}
	var eligible struct {
		Snapshots []restoreSource `json:"snapshots"`
	}
	if err = client.JSON(ctx, "POST", "/api/snapshots/eligible", map[string]any{"scope": scope}, &eligible, 200); err != nil {
		return err
	}
	if len(eligible.Snapshots) != 1 || eligible.Snapshots[0].ID != historical.Snapshot.ID || eligible.Snapshots[0].SkippedCount != 1 || len(eligible.Snapshots[0].SkippedPaths) != 1 || !strings.HasSuffix(eligible.Snapshots[0].SkippedPaths[0], "/protected.txt") {
		return fmt.Errorf("source selection confused historical exclusion with missing coverage: %+v", eligible)
	}
	for _, file := range []struct{ name, content string }{{"allowed.txt", "before restore"}, {"protected.txt", "live protected"}} {
		if err = fixtures.WriteFile(ctx, client, id, "/"+file.name, file.content); err != nil {
			return err
		}
	}
	request := map[string]any{"scope": scope, "source_snapshot_id": historical.Snapshot.ID}
	preview, err := client.RunTaskResult(ctx, "POST", "/api/snapshots/previews", request)
	if err != nil {
		return err
	}
	previewID, _ := preview["preview_id"].(string)
	var previewDetail struct {
		SkippedPaths []string `json:"skipped_paths"`
		SkippedCount int      `json:"skipped_count"`
	}
	if err = client.JSON(ctx, "GET", "/api/snapshots/previews/"+previewID, nil, &previewDetail, 200); err != nil {
		return err
	}
	var actions struct {
		Actions []struct {
			Item string `json:"item"`
		} `json:"actions"`
	}
	if err = client.JSON(ctx, "GET", "/api/snapshots/previews/"+previewID+"/actions", nil, &actions, 200); err != nil {
		return err
	}
	if previewDetail.SkippedCount != 1 || len(previewDetail.SkippedPaths) != 1 || !strings.HasSuffix(previewDetail.SkippedPaths[0], "/protected.txt") || len(actions.Actions) != 1 || !strings.HasSuffix(actions.Actions[0].Item, "/allowed.txt") {
		return fmt.Errorf("preview did not limit changes to the effective selection")
	}
	if err = fixtures.CheckFile(ctx, client, id, "/allowed.txt", "before restore"); err != nil {
		return err
	}
	request["preview_id"] = previewID
	restored, err := client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations", request)
	if err != nil {
		return err
	}
	restorationID, _ := restored["restoration_id"].(string)
	safetyID, _ := restored["safety_snapshot_id"].(string)
	var safety restoreSource
	var snapshots struct {
		Snapshots []restoreSource `json:"snapshots"`
	}
	if err = client.JSON(ctx, "GET", "/api/snapshots", nil, &snapshots, 200); err != nil {
		return err
	}
	for _, snapshot := range snapshots.Snapshots {
		if snapshot.ID == safetyID {
			safety = snapshot
		}
	}
	if len(safety.Paths) != 1 || !strings.HasSuffix(safety.Paths[0], "/allowed.txt") {
		return fmt.Errorf("safety snapshot captured skipped roots: %+v", safety)
	}
	if err = fixtures.CheckFile(ctx, client, id, "/allowed.txt", "source"); err != nil {
		return err
	}
	if err = fixtures.CheckFile(ctx, client, id, "/protected.txt", "live protected"); err != nil {
		return err
	}
	if err = client.RunTask(ctx, "DELETE", "/api/snapshots/previews/"+previewID, nil, nil); err != nil {
		return err
	}
	if err = fixtures.WriteFile(ctx, client, id, "/protected.txt", "after restore"); err != nil {
		return err
	}
	if err = client.RunTask(ctx, "POST", "/api/snapshots/restorations/"+restorationID+"/rollback", nil, nil); err != nil {
		return err
	}
	if err = fixtures.CheckFile(ctx, client, id, "/allowed.txt", "before restore"); err != nil {
		return err
	}
	return fixtures.CheckFile(ctx, client, id, "/protected.txt", "after restore")
}
