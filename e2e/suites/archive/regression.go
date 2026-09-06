package archive

import (
	"bytes"
	"context"
	"crypto/sha256"
	"fmt"
	"net/http"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func begin(ctx context.Context, c *api.Client, name string, data []byte, overwrite bool) (string, error) {
	var result struct {
		ID string `json:"upload_id"`
	}
	err := c.JSON(ctx, "POST", "/api/archive/upload/init", map[string]any{"path": "/", "filename": name, "size": len(data), "allow_overwrite": overwrite}, &result, 200)
	return "/api/archive/upload/" + result.ID, err
}

func publish(ctx context.Context, c *api.Client, name string, data []byte, overwrite bool) error {
	path, err := begin(ctx, c, name, data, overwrite)
	if err != nil {
		return err
	}
	response, err := c.Do(ctx, "PATCH", path, data, http.Header{"Content-Type": {"application/octet-stream"}, "Upload-Offset": {"0"}})
	if err != nil {
		return err
	}
	if err = c.Expect(response, 200); err != nil {
		return err
	}
	event, err := c.SSE(ctx, "GET", path+"/sha256/stream", nil, "complete")
	if err != nil {
		return err
	}
	digest := fmt.Sprintf("%x", sha256.Sum256(data))
	if event["sha256"] != digest {
		return fmt.Errorf("uploaded archive hash differs")
	}
	return c.JSON(ctx, "POST", path+"/verify", map[string]string{"sha256": digest}, nil, 200)
}

func management(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	data, err := payload()
	if err != nil {
		return err
	}
	for _, body := range []map[string]any{{"filename": "../escape.zip", "size": 1}, {"filename": "a.zip", "size": 1, "path": ".."}, {"filename": "a.zip", "size": 0}} {
		expect := 400
		if body["size"] == 0 {
			expect = 422
		}
		if err = c.JSON(ctx, "POST", "/api/archive/upload/init", body, nil, expect); err != nil {
			return err
		}
	}
	path, err := begin(ctx, c, "pending.zip", data, false)
	if err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", path+"/sha256/stream", nil, nil, 409); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", path+"/verify", map[string]string{"sha256": strings.Repeat("0", 64)}, nil, 409); err != nil {
		return err
	}
	for _, chunk := range [][]byte{nil, bytes.Repeat([]byte("x"), len(data)+1)} {
		response, err := c.Do(ctx, "PATCH", path, chunk, http.Header{"Upload-Offset": {"0"}})
		if err != nil {
			return err
		}
		if err = c.Expect(response, 400); err != nil {
			return err
		}
	}
	if err = c.JSON(ctx, "DELETE", path, nil, nil, 204); err != nil {
		return err
	}
	if err = c.JSON(ctx, "HEAD", path, nil, nil, 404); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", "/api/archive/download?path=/pending.zip", nil, nil, 404); err != nil {
		return err
	}
	path, err = begin(ctx, c, "mismatch.zip", data, false)
	if err != nil {
		return err
	}
	response, err := c.Do(ctx, "PATCH", path, data, http.Header{"Upload-Offset": {"0"}})
	if err != nil {
		return err
	}
	if err = c.Expect(response, 200); err != nil {
		return err
	}
	if _, err = c.SSE(ctx, "GET", path+"/sha256/stream", nil, "complete"); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", path+"/verify", map[string]string{"sha256": strings.Repeat("0", 64)}, nil, 409); err != nil {
		return err
	}
	if err = c.JSON(ctx, "HEAD", path, nil, nil, 404); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", "/api/archive/download?path=/mismatch.zip", nil, nil, 404); err != nil {
		return err
	}
	if err = publish(ctx, c, "published.zip", data, false); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/archive/upload/init", map[string]any{"filename": "published.zip", "size": len(data)}, nil, 409); err != nil {
		return err
	}
	changed := append([]byte{}, data...)
	changed = append(changed, []byte("trailing archive comment")...)
	if err = publish(ctx, c, "published.zip", changed, true); err != nil {
		return err
	}
	response, err = c.Do(ctx, "GET", "/api/archive/download?path=/published.zip", nil, nil)
	if err != nil {
		return err
	}
	if err = c.Expect(response, 200); err != nil {
		return err
	}
	if !bytes.Equal(response.Body, changed) {
		return fmt.Errorf("overwrite did not replace archive bytes")
	}
	if err = c.JSON(ctx, "POST", "/api/archive/create", map[string]string{"path": "/", "name": "folder", "type": "directory"}, nil, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/archive/create", map[string]string{"path": "/folder", "name": "empty.zip", "type": "file"}, nil, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/archive/rename", map[string]string{"old_path": "/published.zip", "new_name": "renamed.zip"}, nil, 200); err != nil {
		return err
	}
	var listing struct {
		Items []struct {
			Name string `json:"name"`
		} `json:"items"`
	}
	if err = c.JSON(ctx, "GET", "/api/archive", nil, &listing, 200); err != nil {
		return err
	}
	if len(listing.Items) != 2 {
		return fmt.Errorf("pending/failed uploads leaked into archive listing")
	}
	for _, op := range []struct {
		method, route string
		body          any
		status        int
	}{
		{"GET", "/download?path=/folder", nil, 400}, {"GET", "/download?path=../config.toml", nil, 400},
		{"GET", "?path=..", nil, 400}, {"POST", "/rename", map[string]string{"old_path": "/renamed.zip", "new_name": "../escape.zip"}, 400},
		{"POST", "/create", map[string]string{"path": "/", "name": "folder", "type": "directory"}, 409},
		{"DELETE", "?path=/folder", nil, 200}, {"DELETE", "?path=/renamed.zip", nil, 200},
		{"GET", "/download?path=/renamed.zip", nil, 404}, {"DELETE", "?path=/renamed.zip", nil, 404},
		{"POST", "/compress", map[string]string{"server_id": fixtures.ServerOf(t.Env).ID, "path": "/missing"}, 404},
		{"POST", "/compress", map[string]string{"server_id": fixtures.ServerOf(t.Env).ID, "path": ".."}, 400},
		{"POST", "/compress", map[string]string{"server_id": "missing", "path": "/"}, 404},
	} {
		if err = c.JSON(ctx, op.method, "/api/archive"+op.route, op.body, nil, op.status); err != nil {
			return err
		}
	}
	return nil
}

func cancellation(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	// A real incompressible input keeps the compression task active until cancellation.
	var data strings.Builder
	for n := 0; n < 260000; n++ {
		sum := sha256.Sum256([]byte(fmt.Sprintf("e2e-archive-%d", n)))
		fmt.Fprintf(&data, "%x", sum)
	}
	if err = fixtures.CreateFile(ctx, c, id, "/large.txt", data.String()); err != nil {
		return err
	}
	var task struct {
		ID string `json:"task_id"`
	}
	if err = c.JSON(ctx, "POST", "/api/archive/compress", map[string]string{"server_id": id, "path": "/large.txt"}, &task, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "DELETE", "/api/tasks/"+task.ID, nil, nil, 400); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/tasks/"+task.ID+"/cancel", nil, nil, 200); err != nil {
		return err
	}
	if err = api.Wait(ctx, 100*time.Millisecond, "compression cancelled", func(ctx context.Context) (bool, error) {
		var state struct {
			Status string `json:"status"`
		}
		if err := c.JSON(ctx, "GET", "/api/tasks/"+task.ID, nil, &state, 200); err != nil {
			return false, api.Permanent(err)
		}
		if state.Status == "completed" || state.Status == "failed" {
			return false, api.Permanent(fmt.Errorf("task reached %s instead of cancelled", state.Status))
		}
		return state.Status == "cancelled", nil
	}); err != nil {
		return err
	}
	var listing struct {
		Items []any `json:"items"`
	}
	if err = c.JSON(ctx, "GET", "/api/archive", nil, &listing, 200); err != nil {
		return err
	}
	if len(listing.Items) != 0 {
		return fmt.Errorf("cancelled compression left partial archive")
	}
	return c.JSON(ctx, "DELETE", "/api/tasks/"+task.ID, nil, nil, 200)
}
