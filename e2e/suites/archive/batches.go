package archive

import (
	"context"
	"fmt"
	"net/url"
	"path/filepath"
	"reflect"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func multiPathCompression(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	contents := map[string]string{"a/same.txt": "first", "b/same.txt": "second", "a/@literal[1].txt": "literal", "unselected.txt": "untouched"}
	for path, content := range contents {
		if err = fixtures.CreateFile(ctx, c, id, "/"+path, content); err != nil {
			return err
		}
	}
	if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/files/create", map[string]string{"name": "empty", "path": "/a", "type": "directory"}, nil, 200); err != nil {
		return err
	}
	for _, invalid := range []struct {
		body   map[string]any
		status int
	}{
		{map[string]any{"server_id": id, "paths": []string{"a", "../docker-compose.yml"}}, 400},
		{map[string]any{"server_id": id, "paths": []string{"a", "missing"}}, 404},
		{map[string]any{"server_id": id, "paths": []string{"a"}, "path": "/"}, 422},
	} {
		if err = c.JSON(ctx, "POST", "/api/archive/compress", invalid.body, nil, invalid.status); err != nil {
			return err
		}
	}
	return t.Step("one archive preserves data-relative members, empty folders and literal filenames", func() error {
		var accepted struct {
			ID string `json:"task_id"`
		}
		if err := c.JSON(ctx, "POST", "/api/archive/compress", map[string]any{"server_id": id, "paths": []string{"a", "a/same.txt", "b/same.txt", "a"}}, &accepted, 200); err != nil {
			return err
		}
		task, err := c.Task(ctx, accepted.ID)
		if err != nil {
			return err
		}
		filename, ok := task.Result["filename"].(string)
		if !ok || filename == "" {
			return fmt.Errorf("multi-path archive result missing filename")
		}
		response, err := c.Do(ctx, "GET", "/api/archive/download?path="+url.QueryEscape(filename), nil, nil)
		if err != nil {
			return err
		}
		if err = c.Expect(response, 200); err != nil {
			return err
		}
		if size, ok := task.Result["size"].(float64); !ok || size != float64(len(response.Body)) || size <= 0 {
			return fmt.Errorf("multi-path archive byte count differs")
		}
		backend := fixtures.BackendOf(t.Env)
		archive := filepath.Join("/data/archives", filename)
		listing, err := backend.Docker.Run(ctx, "exec", backend.Name, "7z", "l", "-slt", archive)
		if err != nil {
			return err
		}
		sections := strings.SplitN(listing, "----------\n", 2)
		if len(sections) != 2 {
			return fmt.Errorf("invalid archive listing")
		}
		members := map[string]bool{}
		for _, line := range strings.Split(sections[1], "\n") {
			if strings.HasPrefix(line, "Path = ") {
				members[strings.TrimPrefix(line, "Path = ")] = true
			}
		}
		expected := map[string]bool{"a": true, "a/empty": true, "a/same.txt": true, "a/@literal[1].txt": true, "b/same.txt": true}
		if !reflect.DeepEqual(members, expected) {
			return fmt.Errorf("multi-path archive scope=%v expected=%v", members, expected)
		}
		for _, path := range []string{"a/same.txt", "b/same.txt", "a/@literal[1].txt"} {
			content, err := backend.Docker.Run(ctx, "exec", backend.Name, "7z", "x", "-so", "-spd", archive, path)
			if err != nil {
				return err
			}
			if content != contents[path] {
				return fmt.Errorf("multi-path archive member %s differs", path)
			}
		}
		return fixtures.CheckFile(ctx, c, id, "/unselected.txt", "untouched")
	})
}
