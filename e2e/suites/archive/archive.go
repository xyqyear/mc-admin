package archive

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "archive.upload-populate-compress", Suite: "archive", Tags: []string{"smoke"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: roundtrip},
		{ID: "archive.upload-state-and-management", Suite: "archive", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: management},
		{ID: "archive.task-cancellation", Suite: "archive", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: cancellation},
		{ID: "archive.task-permissions", Suite: "archive", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: taskPermissions},
		{ID: "archive.formats-and-extraction-errors", Suite: "archive", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: formats},
	}
}

func payload() ([]byte, error) {
	var buffer bytes.Buffer
	archive := zip.NewWriter(&buffer)
	for _, file := range []struct{ name, content string }{{"server.properties", "server-port=25565\nlevel-name=world\n"}, {"smoke.txt", "archive round trip\n"}} {
		writer, err := archive.Create(file.name)
		if err != nil {
			return nil, err
		}
		if _, err = writer.Write([]byte(file.content)); err != nil {
			return nil, err
		}
	}
	if err := archive.Close(); err != nil {
		return nil, err
	}
	return buffer.Bytes(), nil
}

func roundtrip(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	data, err := payload()
	if err != nil {
		return err
	}
	var upload struct {
		ID string `json:"upload_id"`
	}
	if err = client.JSON(ctx, "POST", "/api/archive/upload/init", map[string]any{"filename": "smoke.zip", "path": "/", "size": len(data)}, &upload, 200); err != nil {
		return err
	}
	path := "/api/archive/upload/" + upload.ID
	if err = t.Step("resumable upload validates offsets and resumes after a rejected chunk", func() error {
		middle := len(data) / 2
		response, err := client.Do(ctx, "PATCH", path, data[:middle], http.Header{"Content-Type": {"application/octet-stream"}, "Upload-Offset": {"0"}})
		if err != nil {
			return err
		}
		if err = client.Expect(response, 200); err != nil {
			return err
		}
		response, err = client.Do(ctx, "PATCH", path, data[middle:], http.Header{"Content-Type": {"application/octet-stream"}, "Upload-Offset": {"0"}})
		if err != nil {
			return err
		}
		if err = client.Expect(response, 409); err != nil {
			return err
		}
		response, err = client.Do(ctx, "HEAD", path, nil, nil)
		if err != nil {
			return err
		}
		if err = client.Expect(response, 204); err != nil {
			return err
		}
		if response.Header.Get("Upload-Offset") != strconv.Itoa(middle) {
			return fmt.Errorf("rejected chunk changed upload offset")
		}
		response, err = client.Do(ctx, "PATCH", path, data[middle:], http.Header{"Content-Type": {"application/octet-stream"}, "Upload-Offset": {strconv.Itoa(middle)}})
		if err != nil {
			return err
		}
		return client.Expect(response, 200)
	}); err != nil {
		return err
	}
	if err = t.Step("streamed SHA256 matches local bytes and verification publishes the archive", func() error {
		event, err := client.SSE(ctx, "GET", path+"/sha256/stream", nil, "complete")
		if err != nil {
			return err
		}
		digest := fmt.Sprintf("%x", sha256.Sum256(data))
		if event["sha256"] != digest {
			return fmt.Errorf("server SHA256 does not match local archive")
		}
		if err = client.JSON(ctx, "POST", path+"/verify", map[string]string{"sha256": digest}, nil, 200); err != nil {
			return err
		}
		response, err := client.Do(ctx, "GET", "/api/archive/download?path=/smoke.zip", nil, nil)
		if err != nil {
			return err
		}
		if err = client.Expect(response, 200); err != nil {
			return err
		}
		if !bytes.Equal(response.Body, data) {
			return fmt.Errorf("published archive differs from uploaded bytes")
		}
		return nil
	}); err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	if err = t.Step("populate extracts the real archive through a background task", func() error {
		var task struct {
			ID string `json:"task_id"`
		}
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/populate", map[string]string{"archive_filename": "smoke.zip"}, &task, 200); err != nil {
			return err
		}
		if _, err := client.Task(ctx, task.ID); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/smoke.txt", "archive round trip\n")
	}); err != nil {
		return err
	}
	return t.Step("compression produces a downloadable 7z archive and summary-only task lists", func() error {
		var started struct {
			ID string `json:"task_id"`
		}
		if err := client.JSON(ctx, "POST", "/api/archive/compress", map[string]string{"server_id": id, "path": "/"}, &started, 200); err != nil {
			return err
		}
		task, err := client.Task(ctx, started.ID)
		if err != nil {
			return err
		}
		filename, ok := task.Result["filename"].(string)
		if !ok || filename == "" {
			return fmt.Errorf("compression task has no archive filename")
		}
		response, err := client.Do(ctx, "GET", "/api/archive/download?path="+url.QueryEscape("/"+filename), nil, nil)
		if err != nil {
			return err
		}
		if err = client.Expect(response, 200); err != nil {
			return err
		}
		if !bytes.HasPrefix(response.Body, []byte{'7', 'z', 0xbc, 0xaf, 0x27, 0x1c}) {
			return fmt.Errorf("compression output is not a 7z archive")
		}
		firstBytes := response.Body
		if err = client.JSON(ctx, "POST", "/api/servers/"+id+"/files/content?path=/smoke.txt", map[string]string{"content": "second archive contents\n"}, nil, 200); err != nil {
			return err
		}
		if err = client.JSON(ctx, "POST", "/api/archive/compress", map[string]string{"server_id": id, "path": "/"}, &started, 200); err != nil {
			return err
		}
		secondTask, err := client.Task(ctx, started.ID)
		if err != nil {
			return err
		}
		secondFilename, ok := secondTask.Result["filename"].(string)
		if !ok || secondFilename == "" || secondFilename == filename {
			return fmt.Errorf("separate compression tasks must have independent output paths")
		}
		response, err = client.Do(ctx, "GET", "/api/archive/download?path="+url.QueryEscape("/"+filename), nil, nil)
		if err != nil {
			return err
		}
		if err = client.Expect(response, 200); err != nil {
			return err
		}
		if !bytes.Equal(firstBytes, response.Body) {
			return fmt.Errorf("later compression changed the first task's output")
		}
		for _, expected := range []struct{ archive, content string }{
			{filename, "archive round trip\n"}, {secondFilename, "second archive contents\n"},
		} {
			if err = client.JSON(ctx, "POST", "/api/servers/"+id+"/populate", map[string]string{"archive_filename": expected.archive}, &started, 200); err != nil {
				return err
			}
			if _, err = client.Task(ctx, started.ID); err != nil {
				return err
			}
			if err = fixtures.CheckFile(ctx, client, id, "/smoke.txt", expected.content); err != nil {
				return err
			}
		}
		var listed struct {
			Tasks []map[string]any `json:"tasks"`
		}
		if err = client.JSON(ctx, "GET", "/api/tasks", nil, &listed, 200); err != nil {
			return err
		}
		for _, item := range listed.Tasks {
			if _, ok := item["result"]; ok {
				return fmt.Errorf("task list leaks detail payload")
			}
		}
		return nil
	})
}
