package archive

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func formats(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	var tarBytes bytes.Buffer
	writer := tar.NewWriter(&tarBytes)
	for _, file := range []struct{ name, content string }{{"wrapped/server.properties", "server-port=25565\n"}, {"wrapped/nested.txt", "wrapped tar content"}} {
		if err = writer.WriteHeader(&tar.Header{Name: file.name, Mode: 0644, Size: int64(len(file.content))}); err != nil {
			return err
		}
		if _, err = writer.Write([]byte(file.content)); err != nil {
			return err
		}
	}
	if err = writer.Close(); err != nil {
		return err
	}
	if err = publish(ctx, c, "wrapped.tar", tarBytes.Bytes(), false); err != nil {
		return err
	}
	if err = fixtures.CreateFile(ctx, c, id, "/replaced.txt", "old content"); err != nil {
		return err
	}
	var task struct {
		ID string `json:"task_id"`
	}
	if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/populate", map[string]string{"archive_filename": "wrapped.tar"}, &task, 200); err != nil {
		return err
	}
	if _, err = c.Task(ctx, task.ID); err != nil {
		return err
	}
	if err = fixtures.CheckFile(ctx, c, id, "/nested.txt", "wrapped tar content"); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", "/api/servers/"+id+"/files/content?path=/replaced.txt", nil, nil, 404); err != nil {
		return err
	}
	var invalidZip bytes.Buffer
	zipWriter := zip.NewWriter(&invalidZip)
	part, err := zipWriter.Create("readme.txt")
	if err != nil {
		return err
	}
	if _, err = part.Write([]byte("missing required properties")); err != nil {
		return err
	}
	if err = zipWriter.Close(); err != nil {
		return err
	}
	for _, bad := range []struct {
		name    string
		data    []byte
		message string
	}{{"missing-properties.zip", invalidZip.Bytes(), "server.properties"}, {"corrupt.zip", []byte("this is not an archive"), "损坏"}} {
		if err = publish(ctx, c, bad.name, bad.data, false); err != nil {
			return err
		}
		if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/populate", map[string]string{"archive_filename": bad.name}, &task, 200); err != nil {
			return err
		}
		if err = api.Wait(ctx, 100*time.Millisecond, "invalid extraction fails safely", func(ctx context.Context) (bool, error) {
			var state struct {
				Status string `json:"status"`
				Error  string `json:"error"`
			}
			if err := c.JSON(ctx, "GET", "/api/tasks/"+task.ID, nil, &state, 200); err != nil {
				return false, api.Permanent(err)
			}
			if state.Status == "completed" {
				return false, api.Permanent(fmt.Errorf("invalid archive extraction succeeded"))
			}
			if state.Status != "failed" {
				return false, nil
			}
			if !strings.Contains(state.Error, bad.message) {
				return false, api.Permanent(fmt.Errorf("wrong extraction diagnostic: %s", state.Error))
			}
			return true, nil
		}); err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, c, id, "/nested.txt", "wrapped tar content"); err != nil {
			return err
		}
	}
	if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/populate", map[string]string{"archive_filename": "../config.toml"}, nil, 400); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/archive/compress", map[string]string{"server_id": id}, &task, 200); err != nil {
		return err
	}
	completed, err := c.Task(ctx, task.ID)
	if err != nil {
		return err
	}
	filename, ok := completed.Result["filename"].(string)
	if !ok {
		return fmt.Errorf("whole-project compression missing archive")
	}
	if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/populate", map[string]string{"archive_filename": filename}, &task, 200); err != nil {
		return err
	}
	if _, err = c.Task(ctx, task.ID); err != nil {
		return err
	}
	return fixtures.CheckFile(ctx, c, id, "/nested.txt", "wrapped tar content")
}
