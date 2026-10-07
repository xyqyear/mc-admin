package snapshots

import (
	"bytes"
	"compress/gzip"
	"context"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"slices"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type targetRules struct {
	ServerID   string   `json:"server_id"`
	Generation int      `json:"server_generation"`
	Paths      []string `json:"ignored_paths"`
	Version    string   `json:"rules_version"`
}

func logicalExclusions(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	data := filepath.Join(t.Env.Dir, "servers", id, "data")
	for _, directory := range []string{"target", "other"} {
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/files/create", map[string]string{"type": "directory", "path": "/", "name": directory}, nil, 200); err != nil {
			return err
		}
		if err := fixtures.CreateFile(ctx, client, id, "/"+directory+"/value.txt", "source "+directory); err != nil {
			return err
		}
	}
	if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/files/create", map[string]string{"type": "directory", "path": "/target", "name": "region"}, nil, 200); err != nil {
		return err
	}
	var metadata bytes.Buffer
	compressed := gzip.NewWriter(&metadata)
	if _, err := compressed.Write([]byte{10, 0, 0, 0}); err != nil {
		return err
	}
	if err := compressed.Close(); err != nil {
		return err
	}
	for relative, payload := range map[string][]byte{
		"target/level.dat":        metadata.Bytes(),
		"target/region/r.0.0.mca": make([]byte, 8192),
	} {
		if err := os.WriteFile(filepath.Join(data, relative), payload, 0600); err != nil {
			return err
		}
		t.Recorder.Event("fixture_file", map[string]any{"path": relative, "bytes": len(payload)})
	}
	if err := os.Symlink("target", filepath.Join(data, "alias")); err != nil {
		return err
	}
	rulesURL := "/api/snapshots/targets/rules?server_id=" + url.QueryEscape(id)
	if err := updateConfig(ctx, client, func(config map[string]any) {
		config["ignored_paths"] = []string{"alias", "<LEVEL_NAME>/playerdata"}
	}); err != nil {
		return err
	}
	var initial targetRules
	if err := t.Step("shared rules expose logical paths without tasks and require a registered authenticated server", func() error {
		var before []struct {
			ID string `json:"operation_id"`
		}
		if err := client.JSON(ctx, "GET", "/api/operations", nil, &before, 200); err != nil {
			return err
		}
		var beforeTasks struct {
			Total int `json:"total"`
		}
		if err := client.JSON(ctx, "GET", "/api/tasks", nil, &beforeTasks, 200); err != nil {
			return err
		}
		anonymous, err := fixtures.Session(ctx, t, "")
		if err != nil {
			return err
		}
		if err := anonymous.JSON(ctx, "GET", rulesURL, nil, nil, 401); err != nil {
			return err
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/targets/rules?server_id=not-registered", nil, nil, 404); err != nil {
			return err
		}
		if err := client.JSON(ctx, "GET", rulesURL, nil, &initial, 200); err != nil {
			return err
		}
		if initial.ServerID != id || initial.Generation <= 0 || len(initial.Version) != 64 || !slices.Equal(initial.Paths, []string{"alias", "world/playerdata"}) {
			return fmt.Errorf("shared rules did not return logical expanded paths: %+v", initial)
		}
		var detail struct {
			Generation int `json:"server_generation"`
		}
		if err := client.JSON(ctx, "GET", "/api/servers/"+id, nil, &detail, 200); err != nil {
			return err
		}
		if detail.Generation != initial.Generation {
			return fmt.Errorf("server and rules generations differ")
		}
		var history struct {
			Total int `json:"total"`
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/restorations?server_id="+id, nil, &history, 200); err != nil {
			return err
		}
		if history.Total != 0 {
			return fmt.Errorf("reading rules created restoration history")
		}
		var after []struct {
			ID string `json:"operation_id"`
		}
		if err := client.JSON(ctx, "GET", "/api/operations", nil, &after, 200); err != nil {
			return err
		}
		var afterTasks struct {
			Total int `json:"total"`
		}
		if err := client.JSON(ctx, "GET", "/api/tasks", nil, &afterTasks, 200); err != nil {
			return err
		}
		if !slices.Equal(before, after) || beforeTasks.Total != afterTasks.Total {
			return fmt.Errorf("reading rules created operations or tasks")
		}
		return nil
	}); err != nil {
		return err
	}
	pathScope := func(path string) map[string]any {
		return map[string]any{"kind": "paths", "server_id": id, "paths": []string{path}}
	}
	checkWorld := func(path string, allowed bool) error {
		var feedback struct {
			Allowed bool `json:"allowed"`
		}
		body := map[string]any{"scope": map[string]any{"kind": "world", "server_id": id, "selection": map[string]any{"type": "dimension", "region_dir_relpath": path + "/region"}}}
		if err := client.JSON(ctx, "POST", "/api/snapshots/targets/check", body, &feedback, 200); err != nil {
			return err
		}
		if feedback.Allowed != allowed {
			return fmt.Errorf("world scope %s allowed=%v, expected %v", path, feedback.Allowed, allowed)
		}
		return nil
	}
	if err := checkWorld("alias", false); err != nil {
		return err
	}
	if err := checkWorld("target", true); err != nil {
		return err
	}
	if err := client.JSON(ctx, "POST", "/api/snapshots/targets/check", map[string]any{"scope": pathScope("target")}, nil, 422); err != nil {
		return err
	}
	if err := client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"scope": pathScope("alias")}, nil, 400); err != nil {
		return err
	}
	var direct struct {
		Snapshot notedSnapshot `json:"snapshot"`
	}
	if err := client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": pathScope("target")}, &direct); err != nil {
		return err
	}
	if err := updateConfig(ctx, client, func(config map[string]any) { config["ignored_paths"] = []string{"target"} }); err != nil {
		return err
	}
	var changed targetRules
	if err := client.JSON(ctx, "GET", rulesURL, nil, &changed, 200); err != nil {
		return err
	}
	if !slices.Equal(changed.Paths, []string{"target"}) || changed.Version == initial.Version || changed.Generation != initial.Generation {
		return fmt.Errorf("shared rules did not reflect updated configuration: %+v", changed)
	}
	var history struct {
		Snapshots []notedSnapshot `json:"snapshots"`
	}
	if err := client.JSON(ctx, "GET", "/api/snapshots?server_id="+url.QueryEscape(id)+"&path=target", nil, &history, 200); err != nil {
		return err
	}
	if !slices.ContainsFunc(history.Snapshots, func(source notedSnapshot) bool { return source.ID == direct.Snapshot.ID }) {
		return fmt.Errorf("current ignore configuration hid a historical snapshot")
	}
	if err := checkWorld("target", false); err != nil {
		return err
	}
	if err := checkWorld("alias", true); err != nil {
		return err
	}
	if err := client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"scope": pathScope("target")}, nil, 400); err != nil {
		return err
	}
	var alias struct {
		Snapshot notedSnapshot `json:"snapshot"`
	}
	if err := client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": pathScope("alias")}, &alias); err != nil {
		return err
	}
	if err := fixtures.WriteFile(ctx, client, id, "/target/value.txt", "live target"); err != nil {
		return err
	}
	if err := t.Step("allowed alias restores its target and remains reversible after restart", func() error {
		var eligible struct {
			Snapshots []notedSnapshot `json:"snapshots"`
		}
		if err := client.JSON(ctx, "POST", "/api/snapshots/eligible", map[string]any{"scope": pathScope("alias")}, &eligible, 200); err != nil {
			return err
		}
		if !slices.ContainsFunc(eligible.Snapshots, func(source notedSnapshot) bool { return source.ID == alias.Snapshot.ID }) {
			return fmt.Errorf("allowed alias lost its recorded source mapping")
		}
		result, err := client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations", map[string]any{"scope": pathScope("alias"), "source_snapshot_id": alias.Snapshot.ID})
		if err != nil {
			return err
		}
		if err := fixtures.CheckFile(ctx, client, id, "/target/value.txt", "source target"); err != nil {
			return err
		}
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		restorationID, _ := result["restoration_id"].(string)
		if restorationID == "" {
			return fmt.Errorf("alias restore returned no retained history")
		}
		if err := client.RunTask(ctx, "POST", "/api/snapshots/restorations/"+restorationID+"/rollback", nil, nil); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/target/value.txt", "live target")
	}); err != nil {
		return err
	}
	if err := updateConfig(ctx, client, func(config map[string]any) { config["ignored_paths"] = []string{"alias"} }); err != nil {
		return err
	}
	var parent struct {
		Snapshot notedSnapshot `json:"snapshot"`
	}
	if err := client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": pathScope(".")}, &parent); err != nil {
		return err
	}
	if err := os.Remove(filepath.Join(data, "alias")); err != nil {
		return err
	}
	if err := os.Symlink("other", filepath.Join(data, "alias")); err != nil {
		return err
	}
	for _, directory := range []string{"target", "other"} {
		if err := fixtures.WriteFile(ctx, client, id, "/"+directory+"/value.txt", "edited "+directory); err != nil {
			return err
		}
	}
	if err := client.RunTask(ctx, "POST", "/api/snapshots/restorations", map[string]any{"scope": pathScope("."), "source_snapshot_id": parent.Snapshot.ID}, nil); err != nil {
		return err
	}
	if link, err := os.Readlink(filepath.Join(data, "alias")); err != nil || link != "other" {
		return fmt.Errorf("parent restore changed excluded link: target=%q error=%v", link, err)
	}
	if err := fixtures.CheckFile(ctx, client, id, "/target/value.txt", "live target"); err != nil {
		return err
	}
	return fixtures.CheckFile(ctx, client, id, "/other/value.txt", "source other")
}
