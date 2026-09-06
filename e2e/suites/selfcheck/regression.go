package selfcheck

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/url"
	"path/filepath"
	"reflect"
	"strings"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type finding struct {
	Check    string         `json:"check_id"`
	Status   string         `json:"status"`
	Severity string         `json:"severity"`
	Server   string         `json:"server_id"`
	Evidence map[string]any `json:"evidence"`
}
type run struct {
	ID       string    `json:"id"`
	Scope    string    `json:"scope"`
	Check    string    `json:"check_id"`
	Trigger  string    `json:"trigger"`
	Status   string    `json:"status"`
	Findings []finding `json:"findings"`
	Error    *string   `json:"error_message"`
	Summary  struct {
		Total  int `json:"total"`
		Failed int `json:"failed"`
	} `json:"summary"`
}

func single(ctx context.Context, c *api.Client, id string) (run, error) {
	var result run
	err := c.JSON(ctx, "POST", "/api/self-check/checks/"+id+"/run", nil, &result, 200)
	if err == nil && (result.ID == "" || result.Scope != "check" || result.Check != id || len(result.Findings) == 0 || result.Error != nil) {
		err = fmt.Errorf("invalid single-check run for %s", id)
	}
	return result, err
}

func expectFinding(result run, check, status string) error {
	for _, f := range result.Findings {
		if f.Check == check {
			if f.Status != status {
				return fmt.Errorf("%s status %s, expected %s (evidence %v)", check, f.Status, status, f.Evidence)
			}
			return nil
		}
	}
	return fmt.Errorf("run omitted %s", check)
}

func history(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	var catalog []struct {
		Check   string `json:"check_id"`
		Enabled bool   `json:"enabled"`
	}
	if err = c.JSON(ctx, "GET", "/api/self-check/catalog", nil, &catalog, 200); err != nil {
		return err
	}
	if len(catalog) != 15 {
		return fmt.Errorf("expected 15 documented checks, got %d; update scenario for catalog changes", len(catalog))
	}
	var full run
	if err = t.Step("full self-check runs every registered check and persists all healthy and unhealthy findings", func() error {
		if err := c.JSON(ctx, "POST", "/api/self-check/run", nil, &full, 200); err != nil {
			return err
		}
		if full.ID == "" || full.Scope != "full" || full.Trigger != "manual" || full.Error != nil || full.Summary.Total != len(full.Findings) {
			return fmt.Errorf("full run result is incomplete")
		}
		for _, entry := range catalog {
			found := false
			for _, f := range full.Findings {
				if f.Check == entry.Check {
					found = true
					if f.Severity == "critical" || f.Status == "failed" {
						return fmt.Errorf("self-check %s unexpectedly failed", entry.Check)
					}
				}
			}
			if !found {
				return fmt.Errorf("full run omitted %s", entry.Check)
			}
		}
		if err := expectFinding(full, "backup.restic_configured", "warning"); err != nil {
			return err
		}
		if err := expectFinding(full, "dependency.binaries", "passed"); err != nil {
			return err
		}
		var detail run
		if err := c.JSON(ctx, "GET", "/api/self-check/runs/"+full.ID, nil, &detail, 200); err != nil {
			return err
		}
		if !reflect.DeepEqual(full.Findings, detail.Findings) {
			return fmt.Errorf("retained findings differ from execution result")
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("streamed execution reports each started/finished check and stores its terminal result", func() error {
		started, finished := map[string]bool{}, map[string]bool{}
		event, err := c.SSEEvents(ctx, "POST", "/api/self-check/run/stream", nil, "completed", func(event map[string]any) error {
			id, _ := event["check_id"].(string)
			switch event["type"] {
			case "check_started":
				if started[id] {
					return fmt.Errorf("duplicate check start %s", id)
				}
				started[id] = true
			case "check_finished":
				if !started[id] || finished[id] {
					return fmt.Errorf("out-of-order check completion %s", id)
				}
				finished[id] = true
			}
			return nil
		})
		if err != nil {
			return err
		}
		if len(started) != len(catalog) || len(finished) != len(catalog) {
			return fmt.Errorf("stream omitted check transitions")
		}
		data, err := json.Marshal(event["result"])
		if err != nil {
			return err
		}
		var streamed run
		if err = json.Unmarshal(data, &streamed); err != nil {
			return err
		}
		if streamed.ID == "" || streamed.Error != nil || len(streamed.Findings) == 0 {
			return fmt.Errorf("stream has no valid result")
		}
		return c.JSON(ctx, "GET", "/api/self-check/runs/"+streamed.ID, nil, nil, 200)
	}); err != nil {
		return err
	}
	for _, entry := range catalog {
		result, err := single(ctx, c, entry.Check)
		if err != nil {
			return err
		}
		for _, f := range result.Findings {
			if f.Check != entry.Check || f.Status == "failed" {
				return fmt.Errorf("single-check %s returned unrelated or failed finding", entry.Check)
			}
		}
	}
	return t.Step("history pagination and status keep completed runs across restart", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		var history struct {
			Total int   `json:"total"`
			Runs  []run `json:"runs"`
		}
		if err := c.JSON(ctx, "GET", "/api/self-check/runs?limit=2&offset=1", nil, &history, 200); err != nil {
			return err
		}
		if history.Total < 17 || len(history.Runs) != 2 {
			return fmt.Errorf("unexpected retained history total=%d page=%d", history.Total, len(history.Runs))
		}
		if err := c.JSON(ctx, "GET", "/api/self-check/runs/"+full.ID, nil, nil, 200); err != nil {
			return err
		}
		var status struct {
			State *struct {
				Findings []finding `json:"findings"`
			} `json:"current_state"`
		}
		if err := c.JSON(ctx, "GET", "/api/self-check/status", nil, &status, 200); err != nil {
			return err
		}
		if status.State == nil || len(status.State.Findings) == 0 {
			return fmt.Errorf("status omitted derived current health")
		}
		for _, path := range []string{"/api/self-check/runs?limit=0", "/api/self-check/runs?offset=-1"} {
			if err := c.JSON(ctx, "GET", path, nil, nil, 422); err != nil {
				return err
			}
		}
		if err := c.JSON(ctx, "GET", "/api/self-check/runs/missing", nil, nil, 404); err != nil {
			return err
		}
		return c.JSON(ctx, "POST", "/api/self-check/checks/missing/run", nil, nil, 404)
	})
}

func gamePort(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	result, err := single(ctx, c, "server.game_port_consistency")
	if err != nil {
		return err
	}
	if err = expectFinding(result, "server.game_port_consistency", "skipped"); err != nil {
		return err
	}
	if err = fixtures.CreateFile(ctx, c, id, "/server.properties", "server-port=25566\n"); err != nil {
		return err
	}
	var full run
	if err = c.JSON(ctx, "POST", "/api/self-check/run", nil, &full, 200); err != nil {
		return err
	}
	if err = expectFinding(full, "server.game_port_consistency", "warning"); err != nil {
		return err
	}
	if err = t.Step("game port compares final property assignment with container target and retains history", func() error {
		if err := fixtures.WriteFile(ctx, c, id, "/server.properties", "server-port=12345\nserver-port=25565\n"); err != nil {
			return err
		}
		fixed, err := single(ctx, c, "server.game_port_consistency")
		if err != nil {
			return err
		}
		if err = expectFinding(fixed, "server.game_port_consistency", "passed"); err != nil {
			return err
		}
		if fixed.Findings[0].Evidence["expected_container_port"] != float64(25565) || fixed.Findings[0].Evidence["published_game_port"] != fmt.Sprint(fixtures.ServerOf(t.Env).GamePort) {
			return fmt.Errorf("port evidence confused host and container ports")
		}
		var status struct {
			State struct {
				Findings []finding `json:"findings"`
			} `json:"current_state"`
		}
		if err = c.JSON(ctx, "GET", "/api/self-check/status", nil, &status, 200); err != nil {
			return err
		}
		if err = expectFinding(run{Findings: status.State.Findings}, "server.game_port_consistency", "passed"); err != nil {
			return err
		}
		var historical run
		if err = c.JSON(ctx, "GET", "/api/self-check/runs/"+full.ID, nil, &historical, 200); err != nil {
			return err
		}
		return expectFinding(historical, "server.game_port_consistency", "warning")
	}); err != nil {
		return err
	}
	if err = fixtures.WriteFile(ctx, c, id, "/server.properties", "server-port=invalid\n"); err != nil {
		return err
	}
	result, err = single(ctx, c, "server.game_port_consistency")
	if err != nil {
		return err
	}
	if err = expectFinding(result, "server.game_port_consistency", "failed"); err != nil {
		return err
	}
	return t.Step("disabled checks disappear from current state while retained failure evidence survives", func() error {
		var config struct {
			Data map[string]any `json:"config_data"`
		}
		if err := c.JSON(ctx, "GET", "/api/config/modules/self_check", nil, &config, 200); err != nil {
			return err
		}
		checks, ok := config.Data["checks"].(map[string]any)
		if !ok {
			return fmt.Errorf("self-check config omitted switches")
		}
		checks["server_game_port_consistency"] = false
		if err := c.JSON(ctx, "PUT", "/api/config/modules/self_check", map[string]any{"config_data": config.Data}, nil, 200); err != nil {
			return err
		}
		var status struct {
			State struct {
				Findings []finding `json:"findings"`
			} `json:"current_state"`
		}
		if err := c.JSON(ctx, "GET", "/api/self-check/status", nil, &status, 200); err != nil {
			return err
		}
		for _, f := range status.State.Findings {
			if f.Check == "server.game_port_consistency" {
				return fmt.Errorf("disabled check still affects current health")
			}
		}
		var retained run
		if err := c.JSON(ctx, "GET", "/api/self-check/runs/"+result.ID, nil, &retained, 200); err != nil {
			return err
		}
		if err := expectFinding(retained, "server.game_port_consistency", "failed"); err != nil {
			return err
		}
		disabled, err := single(ctx, c, "server.game_port_consistency")
		if err != nil {
			return err
		}
		return expectFinding(disabled, "server.game_port_consistency", "skipped")
	})
}

func jarMetadata(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	for _, directory := range []string{"mods", "plugins"} {
		if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/files/create", map[string]string{"name": directory, "path": "/", "type": "directory"}, nil, 200); err != nil {
			return err
		}
	}
	if err = t.Step("backup detection reads jar metadata IDs instead of misleading filenames", func() error {
		for _, format := range []struct{ path, metadata, content string }{
			{"/mods", "fabric.mod.json", `{"schemaVersion":1,"id":"FTBBackups2","version":"1.0","name":"Ordinary mod"}`},
			{"/mods", "quilt.mod.json", `{"schema_version":1,"quilt_loader":{"group":"invalid.e2e","version":"1.0.0","intermediate_mappings":"net.fabricmc:intermediary","depends":[{"id":"unrelated_dependency","versions":"*"}],"id":"ftbbackups2","metadata":{"name":"Ordinary mod"}}}`},
			{"/mods", "META-INF/mods.toml", "[[mods]]\nmodId = \"FTBBackups2\"\n"},
			{"/mods", "META-INF/neoforge.mods.toml", "[[mods]]\nmodId = \"FTBBackups2\"\n"},
			{"/mods", "mcmod.info", `[{"modid":"FTBBackups2","version":"1.0"}]`},
			{"/plugins", "plugin.yml", "name: FTBBackups2\nversion: '1.0'\nmain: e2e.BackupPlugin\n"},
			{"/plugins", "paper-plugin.yml", "name: FTBBackups2\nversion: '1.0'\nmain: e2e.BackupPlugin\n"},
		} {
			if err = uploadJarMetadata(ctx, c, id, format.path, format.metadata, format.content); err != nil {
				return err
			}
			result, err := single(ctx, c, "server.backup_mod_removed")
			if err != nil {
				return err
			}
			if err = expectFinding(result, "server.backup_mod_removed", "warning"); err != nil {
				return fmt.Errorf("%s: %w", format.metadata, err)
			}
			encoded, _ := json.Marshal(result.Findings[0].Evidence)
			if !bytes.Contains(encoded, []byte("ordinary.jar")) || !bytes.Contains(encoded, []byte("ftbbackups2")) || !bytes.Contains(encoded, []byte(format.metadata)) {
				return fmt.Errorf("jar evidence omitted matched file and metadata ID")
			}
			if err = c.JSON(ctx, "DELETE", "/api/servers/"+id+"/files?path="+url.QueryEscape(format.path+"/ordinary.jar"), nil, nil, 200); err != nil {
				return err
			}
		}
		if err = fixtures.CreateFile(ctx, c, id, "/mods/ftbbackups2.jar", "not a jar"); err != nil {
			return err
		}
		result, err := single(ctx, c, "server.backup_mod_removed")
		if err != nil {
			return err
		}
		return expectFinding(result, "server.backup_mod_removed", "passed")
	}); err != nil {
		return err
	}
	if err = t.Step("Quilt dependency IDs and malformed metadata do not identify a backup mod", func() error {
		for _, fixture := range []struct{ name, content string }{
			{"dependency before own ID", `{"schema_version":1,"quilt_loader":{"depends":[{"id":"ftbbackups2","versions":"*"}],"group":"invalid.e2e","id":"ordinary_mod","version":"1.0.0","intermediate_mappings":"net.fabricmc:intermediary"}}`},
			{"truncated after dependency", `{"schema_version":1,"quilt_loader":{"depends":[{"id":"ftbbackups2","versions":"*"}],`},
			{"trailing comma after own ID", `{"schema_version":1,"quilt_loader":{"group":"invalid.e2e","id":"ftbbackups2","version":"1.0.0",}}`},
		} {
			if err := uploadJarMetadata(ctx, c, id, "/mods", "quilt.mod.json", fixture.content); err != nil {
				return err
			}
			result, err := single(ctx, c, "server.backup_mod_removed")
			if err != nil {
				return err
			}
			if err = expectFinding(result, "server.backup_mod_removed", "passed"); err != nil {
				return fmt.Errorf("%s: %w", fixture.name, err)
			}
			if err = c.JSON(ctx, "DELETE", "/api/servers/"+id+"/files?path="+url.QueryEscape("/mods/ordinary.jar"), nil, nil, 200); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("real ownership mismatch is detected and API repair restores consistency", func() error {
		if err := fixtures.CreateFile(ctx, c, id, "/ownership.txt", "owner repair"); err != nil {
			return err
		}
		b := fixtures.BackendOf(t.Env)
		if _, err := b.Docker.Run(ctx, "exec", b.Name, "chown", "12345:12345", filepath.Join(t.Env.Dir, "servers", id, "data", "ownership.txt")); err != nil {
			return err
		}
		result, err := single(ctx, c, "files.permission_consistency")
		if err != nil {
			return err
		}
		if err = expectFinding(result, "files.permission_consistency", "warning"); err != nil {
			return err
		}
		var task struct {
			ID string `json:"task_id"`
		}
		if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/files/ownership/restore", nil, &task, 200); err != nil {
			return err
		}
		if _, err = c.Task(ctx, task.ID); err != nil {
			return err
		}
		result, err = single(ctx, c, "files.permission_consistency")
		if err != nil {
			return err
		}
		return expectFinding(result, "files.permission_consistency", "passed")
	})
}

func uploadJarMetadata(ctx context.Context, c *api.Client, id, directory, metadata, content string) error {
	var data bytes.Buffer
	writer := zip.NewWriter(&data)
	entry, err := writer.Create(metadata)
	if err != nil {
		return err
	}
	if _, err = entry.Write([]byte(content)); err != nil {
		return err
	}
	if err = writer.Close(); err != nil {
		return err
	}
	return upload(ctx, c, id, directory, "ordinary.jar", data.Bytes())
}

func upload(ctx context.Context, c *api.Client, id, path, name string, data []byte) error {
	base := "/api/servers/" + id + "/files/upload"
	var prepared struct {
		ID string `json:"session_id"`
	}
	if err := c.JSON(ctx, "POST", base+"/check?path="+url.QueryEscape(path), map[string]any{"files": []any{map[string]any{"path": name, "name": name, "type": "file", "size": len(data)}}}, &prepared, 200); err != nil {
		return err
	}
	if prepared.ID == "" {
		return fmt.Errorf("upload session missing")
	}
	if err := c.JSON(ctx, "POST", base+"/policy?session_id="+url.QueryEscape(prepared.ID), map[string]string{"mode": "always_overwrite"}, nil, 200); err != nil {
		return err
	}
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("files", name)
	if err != nil {
		return err
	}
	if _, err = part.Write(data); err != nil {
		return err
	}
	if err = writer.Close(); err != nil {
		return err
	}
	response, err := c.Do(ctx, "POST", base+"/multiple?session_id="+url.QueryEscape(prepared.ID)+"&path="+url.QueryEscape(path), body.Bytes(), http.Header{"Content-Type": {writer.FormDataContentType()}})
	if err != nil {
		return err
	}
	if err = c.Expect(response, 200); err != nil {
		return err
	}
	var result struct {
		Results map[string]struct {
			Status string `json:"status"`
		} `json:"results"`
	}
	if err = json.Unmarshal(response.Body, &result); err != nil {
		return err
	}
	if len(result.Results) != 1 {
		return fmt.Errorf("jar upload did not return one result")
	}
	for _, file := range result.Results {
		if file.Status != "success" {
			return fmt.Errorf("jar upload ended %s", file.Status)
		}
	}
	return nil
}

func repositoryHealth(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	return t.Step("real Restic repository, snapshot coverage, freshness and idle locks report healthy", func() error {
		var config struct {
			Data map[string]any `json:"config_data"`
		}
		if err := c.JSON(ctx, "GET", "/api/config/modules/self_check", nil, &config, 200); err != nil {
			return err
		}
		config.Data["backup_repository_usage_percent"] = 100
		if err := c.JSON(ctx, "PUT", "/api/config/modules/self_check", map[string]any{"config_data": config.Data}, nil, 200); err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", "/api/snapshots", map[string]string{"server_id": fixtures.ServerOf(t.Env).ID}, nil, 200); err != nil {
			return err
		}
		for _, check := range []string{"backup.restic_configured", "backup.restic_reachable", "backup.server_snapshot_coverage", "backup.server_snapshot_freshness", "storage.backup_repository_usage", "locks.python_restic_active", "locks.repo_restic_active"} {
			result, err := single(ctx, c, check)
			if err != nil {
				return err
			}
			if strings.HasPrefix(check, "locks.") {
				for _, f := range result.Findings {
					if f.Severity == "warning" || f.Severity == "critical" || f.Status == "failed" {
						return fmt.Errorf("idle lock health unexpected: %+v", f)
					}
				}
			} else if err = expectFinding(result, check, "passed"); err != nil {
				return err
			}
		}
		return nil
	})
}

func dependencyAndFilesystem(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	b := fixtures.BackendOf(t.Env)
	if err = t.Step("dependency health detects and recovers a missing executable permission", func() error {
		if _, err := b.Docker.Run(ctx, "exec", b.Name, "chmod", "-x", "/usr/local/bin/mcmap"); err != nil {
			return err
		}
		result, err := single(ctx, c, "dependency.binaries")
		if err != nil {
			return err
		}
		if err = expectFinding(result, "dependency.binaries", "warning"); err != nil {
			return err
		}
		encoded, _ := json.Marshal(result.Findings[0].Evidence)
		if !bytes.Contains(encoded, []byte("mcmap")) {
			return fmt.Errorf("dependency warning omitted unavailable mcmap")
		}
		if _, err = b.Docker.Run(ctx, "exec", b.Name, "chmod", "+x", "/usr/local/bin/mcmap"); err != nil {
			return err
		}
		result, err = single(ctx, c, "dependency.binaries")
		if err != nil {
			return err
		}
		return expectFinding(result, "dependency.binaries", "passed")
	}); err != nil {
		return err
	}
	return t.Step("filesystem drift reports missing database-backed projects and recovers after their return", func() error {
		id := fixtures.ServerOf(t.Env).ID
		project := filepath.Join(t.Env.Dir, "servers", id)
		if _, err := b.Docker.Run(ctx, "exec", b.Name, "mv", project, "/data/displaced-project"); err != nil {
			return err
		}
		result, err := single(ctx, c, "server.filesystem_db_sync")
		if err != nil {
			return err
		}
		if err = expectFinding(result, "server.filesystem_db_sync", "warning"); err != nil {
			return err
		}
		missing, ok := result.Findings[0].Evidence["database_only"].([]any)
		if !ok || len(missing) != 1 || missing[0] != id {
			return fmt.Errorf("filesystem drift omitted missing server identity")
		}
		if _, err = b.Docker.Run(ctx, "exec", b.Name, "mv", "/data/displaced-project", project); err != nil {
			return err
		}
		result, err = single(ctx, c, "server.filesystem_db_sync")
		if err != nil {
			return err
		}
		return expectFinding(result, "server.filesystem_db_sync", "passed")
	})
}
