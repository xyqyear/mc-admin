package files

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func multipartSafeFailures(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id + "/files"
	const marker = "owned-upload-sensitive-adapter-path"
	t.Recorder.Redactor.Add(marker)
	if err = c.JSON(ctx, "POST", base+"/create", map[string]string{"path": "/", "name": marker, "type": "directory"}, nil, 200); err != nil {
		return err
	}
	for _, reusable := range []bool{false, true} {
		var session struct {
			ID string `json:"session_id"`
		}
		if err = c.JSON(ctx, "POST", base+"/upload/check?path=/", map[string]any{"files": []any{}}, &session, 200); err != nil {
			return err
		}
		if err = c.JSON(ctx, "POST", fmt.Sprintf("%s/upload/policy?session_id=%s&reusable=%t", base, session.ID, reusable), map[string]string{"mode": "always_overwrite"}, nil, 200); err != nil {
			return err
		}
		route := base + "/upload/multiple?path=/&session_id=" + session.ID
		body, contentType, err := api.MultipartFiles([]api.FilePart{
			{Filename: marker, Content: []byte("must not replace the existing directory")},
			{Filename: "continued.txt", Content: []byte(fmt.Sprintf("continued after failure reusable=%t\n", reusable))},
		})
		if err != nil {
			return err
		}
		response, err := c.Do(ctx, "POST", route, body, http.Header{"Content-Type": {contentType}})
		if err != nil {
			return err
		}
		if err = c.Expect(response, 200); err != nil {
			return err
		}
		var result struct {
			Results map[string]struct{ Status, Reason string } `json:"results"`
		}
		if err = json.Unmarshal(response.Body, &result); err != nil {
			return err
		}
		if len(result.Results) != 2 || result.Results[marker].Status != "failed" || result.Results[marker].Reason != "文件上传失败，请稍后重试" || result.Results["continued.txt"].Status != "success" {
			return fmt.Errorf("member failure did not retain safe detail and the next member's successful result")
		}
		if err = fixtures.CheckFile(ctx, c, id, "/continued.txt", fmt.Sprintf("continued after failure reusable=%t\n", reusable)); err != nil {
			return err
		}
		written, err := os.ReadFile(filepath.Join(t.Env.Dir, "servers", id, "data", "continued.txt"))
		if err != nil {
			return err
		}
		if string(written) != fmt.Sprintf("continued after failure reusable=%t\n", reusable) {
			return fmt.Errorf("the member after the failure has incorrect owned filesystem bytes")
		}
		failedTarget, err := os.Stat(filepath.Join(t.Env.Dir, "servers", id, "data", marker))
		if err != nil {
			return err
		}
		if !failedTarget.IsDir() {
			return fmt.Errorf("failed upload replaced its existing directory")
		}
		status := 404
		if reusable {
			status = 200
		}
		if _, err = upload(ctx, c, route, map[string]string{"continued.txt": "session timing remains intact\n"}, status); err != nil {
			return err
		}
	}
	if err = fixtures.CreateFile(ctx, c, id, "/blocked-parent", "parent remains a file\n"); err != nil {
		return err
	}
	var session struct {
		ID string `json:"session_id"`
	}
	if err = c.JSON(ctx, "POST", base+"/upload/check?path=/", map[string]any{"files": []any{}}, &session, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", base+"/upload/policy?session_id="+session.ID, map[string]string{"mode": "always_overwrite"}, nil, 200); err != nil {
		return err
	}
	body, contentType, err := api.MultipartFiles([]api.FilePart{
		{Filename: "blocked-parent/" + marker + "/first.txt", Content: []byte("unwritten")},
		{Filename: "after-outer-failure.txt", Content: []byte("unwritten")},
	})
	if err != nil {
		return err
	}
	response, err := c.Do(ctx, "POST", base+"/upload/multiple?path=/&session_id="+session.ID, body, http.Header{"Content-Type": {contentType}})
	if err != nil {
		return err
	}
	if err = c.Expect(response, 500); err != nil {
		return err
	}
	var failure struct {
		Detail string `json:"detail"`
	}
	if err = json.Unmarshal(response.Body, &failure); err != nil {
		return err
	}
	if failure.Detail != "文件上传失败，请稍后重试" {
		return fmt.Errorf("outer upload failure exposed adapter detail")
	}
	if err = fixtures.CheckFile(ctx, c, id, "/blocked-parent", "parent remains a file\n"); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", base+"/content?path=/after-outer-failure.txt", nil, nil, 404); err != nil {
		return err
	}
	if _, err = upload(ctx, c, base+"/upload/multiple?path=/&session_id="+session.ID, map[string]string{"after-outer-failure.txt": "unwritten"}, 404); err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	logs, err := backend.Docker.Run(ctx, "logs", backend.Name)
	if err != nil {
		return err
	}
	applicationLog, err := os.ReadFile(filepath.Join(t.Env.Dir, "logs", "app.log"))
	if err != nil {
		return err
	}
	for _, output := range []string{logs, string(applicationLog)} {
		if !strings.Contains(output, "File upload failed: IsADirectoryError") || !strings.Contains(output, "Multi-file upload failed: NotADirectoryError") || strings.Contains(output, marker) {
			return fmt.Errorf("real member and outer failure logs lack safe diagnostics or expose adapter paths")
		}
	}
	return nil
}
