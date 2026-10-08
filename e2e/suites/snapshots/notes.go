package snapshots

import (
	"context"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type notedSnapshot struct {
	ID   string `json:"id"`
	Note string `json:"note"`
}

func notesAndMultiplePaths(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	for _, file := range []struct{ name, content string }{{"one.txt", "source one"}, {"two.txt", "source two"}, {"unselected.txt", "source unselected"}} {
		if err = fixtures.CreateFile(ctx, client, id, "/"+file.name, file.content); err != nil {
			return err
		}
	}
	scope := map[string]any{"kind": "paths", "server_id": id, "paths": []string{"one.txt", "two.txt"}}
	var created struct {
		Snapshot    notedSnapshot `json:"snapshot"`
		NoteWarning *string       `json:"note_warning"`
	}
	if err = client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": scope, "note": "变更前的中文备注"}, &created); err != nil {
		return err
	}
	if len(created.Snapshot.ID) != 64 || created.Snapshot.Note != "变更前的中文备注" || created.NoteWarning != nil {
		return fmt.Errorf("creation lost snapshot identity or persisted note: %+v", created)
	}
	for _, file := range []struct{ name, content string }{{"one.txt", "before one"}, {"two.txt", "before two"}, {"unselected.txt", "unselected live"}} {
		if err = fixtures.WriteFile(ctx, client, id, "/"+file.name, file.content); err != nil {
			return err
		}
	}
	preview, err := client.RunTaskResult(ctx, "POST", "/api/snapshots/previews", map[string]any{"scope": scope, "source_snapshot_id": created.Snapshot.ID})
	if err != nil {
		return err
	}
	previewID, _ := preview["preview_id"].(string)
	if previewID == "" {
		return fmt.Errorf("multi-path preview returned no identity")
	}
	if err = t.Step("note edits preserve identity and an existing multi-path preview", func() error {
		anonymous, err := fixtures.Session(ctx, t, "")
		if err != nil {
			return err
		}
		path := "/api/snapshots/" + created.Snapshot.ID + "/note"
		if err := anonymous.JSON(ctx, "PUT", path, map[string]string{"note": "拒绝匿名写入"}, nil, 401); err != nil {
			return err
		}
		client.CSRF = false
		csrfError := client.JSON(ctx, "PUT", path, map[string]string{"note": "拒绝无校验写入"}, nil, 403)
		client.CSRF = true
		if csrfError != nil {
			return csrfError
		}
		if err := client.JSON(ctx, "PUT", path, map[string]string{"note": strings.Repeat("字", 501)}, nil, 422); err != nil {
			return err
		}
		if err := client.JSON(ctx, "PUT", "/api/snapshots/"+created.Snapshot.ID[:8]+"/note", map[string]string{"note": "短 ID"}, nil, 422); err != nil {
			return err
		}
		var updated notedSnapshot
		if err := client.JSON(ctx, "PUT", path, map[string]string{"note": "恢复所用的中文备注"}, &updated, 200); err != nil {
			return err
		}
		if updated.ID != created.Snapshot.ID || updated.Note != "恢复所用的中文备注" {
			return fmt.Errorf("note edit changed snapshot identity or lost content")
		}
		var eligible struct {
			Snapshots []notedSnapshot `json:"snapshots"`
		}
		if err := client.JSON(ctx, "POST", "/api/snapshots/eligible", map[string]any{"scope": scope}, &eligible, 200); err != nil {
			return err
		}
		if len(eligible.Snapshots) != 1 || eligible.Snapshots[0] != updated {
			return fmt.Errorf("eligible multi-path source did not project the same note")
		}
		return client.JSON(ctx, "GET", "/api/snapshots/previews/"+previewID, nil, nil, 200)
	}); err != nil {
		return err
	}
	restored, err := client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations", map[string]any{
		"scope": scope, "source_snapshot_id": created.Snapshot.ID, "preview_id": previewID,
	})
	if err != nil {
		return err
	}
	restorationID, _ := restored["restoration_id"].(string)
	safetyID, _ := restored["safety_snapshot_id"].(string)
	if restorationID == "" || len(safetyID) != 64 {
		return fmt.Errorf("multi-path restoration did not share retained history and safety snapshot")
	}
	for _, file := range []struct{ name, content string }{{"one.txt", "source one"}, {"two.txt", "source two"}, {"unselected.txt", "unselected live"}} {
		if err = fixtures.CheckFile(ctx, client, id, "/"+file.name, file.content); err != nil {
			return err
		}
	}
	if err = client.RunTask(ctx, "DELETE", "/api/snapshots/previews/"+previewID, nil, nil); err != nil {
		return err
	}
	if err = client.JSON(ctx, "PUT", "/api/snapshots/"+safetyID+"/note", map[string]string{"note": "恢复前的安全状态"}, nil, 200); err != nil {
		return err
	}
	if err = t.Step("notes and restoration references survive application restart and remain reversible", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		var listed struct {
			Snapshots []notedSnapshot `json:"snapshots"`
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots", nil, &listed, 200); err != nil {
			return err
		}
		actual := map[string]string{}
		for _, snapshot := range listed.Snapshots {
			actual[snapshot.ID] = snapshot.Note
		}
		if len(actual) != 2 || actual[created.Snapshot.ID] != "恢复所用的中文备注" || actual[safetyID] != "恢复前的安全状态" {
			return fmt.Errorf("restart lost persisted notes or changed repository snapshot identities")
		}
		var history struct {
			SourceID  string `json:"source_snapshot_id"`
			SafetyID  string `json:"safety_snapshot_id"`
			Available bool   `json:"rollback_available"`
		}
		if err := client.JSON(ctx, "GET", "/api/snapshots/restorations/"+restorationID, nil, &history, 200); err != nil {
			return err
		}
		if history.SourceID != created.Snapshot.ID || history.SafetyID != safetyID || !history.Available {
			return fmt.Errorf("note edits or restart broke restoration references")
		}
		if err := client.RunTask(ctx, "POST", "/api/snapshots/restorations/"+restorationID+"/rollback", nil, nil); err != nil {
			return err
		}
		for _, file := range []struct{ name, content string }{{"one.txt", "before one"}, {"two.txt", "before two"}, {"unselected.txt", "unselected live"}} {
			if err := fixtures.CheckFile(ctx, client, id, "/"+file.name, file.content); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("a historical source skipping one selected root remains eligible", func() error {
		if err := updateConfig(ctx, client, func(config map[string]any) { config["ignored_paths"] = []string{"two.txt"} }); err != nil {
			return err
		}
		var excluded struct {
			Snapshot notedSnapshot `json:"snapshot"`
		}
		if err := client.RunTask(ctx, "POST", "/api/snapshots", map[string]any{"scope": map[string]any{"kind": "global"}}, &excluded); err != nil {
			return err
		}
		if excluded.Snapshot.Note != "" {
			return fmt.Errorf("snapshot created without a note did not default to empty")
		}
		if err := updateConfig(ctx, client, func(config map[string]any) { config["ignored_paths"] = []string{".mcmap"} }); err != nil {
			return err
		}
		var eligible struct {
			Snapshots []notedSnapshot `json:"snapshots"`
		}
		if err := client.JSON(ctx, "POST", "/api/snapshots/eligible", map[string]any{"scope": scope}, &eligible, 200); err != nil {
			return err
		}
		found, foundExcluded := false, false
		for _, snapshot := range eligible.Snapshots {
			foundExcluded = foundExcluded || snapshot.ID == excluded.Snapshot.ID
			found = found || snapshot.ID == created.Snapshot.ID
		}
		if !found || !foundExcluded {
			return fmt.Errorf("eligible sources lost full coverage or historical skip semantics")
		}
		return nil
	})
}
