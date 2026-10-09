package files

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"reflect"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type manifestEntry struct {
	Path string `json:"path"`
	Type string `json:"type"`
	Size int64  `json:"size"`
}

type downloadManifest struct {
	Generation int             `json:"server_generation"`
	Entries    []manifestEntry `json:"entries"`
	Errors     []struct {
		Path string `json:"path"`
	} `json:"errors"`
}

func batchManifestDelete(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id + "/files"
	contents := map[string]string{"selected/a/same.txt": "first", "selected/b/same.txt": "second", "unselected.txt": "untouched"}
	for path, content := range contents {
		if err = fixtures.CreateFile(ctx, c, id, "/"+path, content); err != nil {
			return err
		}
	}
	if err = c.JSON(ctx, "POST", base+"/create", map[string]string{"name": "empty", "path": "/selected", "type": "directory"}, nil, 200); err != nil {
		return err
	}
	bulk := filepath.Join(t.Env.Dir, "servers", id, "data", "selected", "bulk")
	if err = os.MkdirAll(bulk, 0o755); err != nil {
		return err
	}
	for index := 0; index < 240; index++ {
		if err = os.WriteFile(filepath.Join(bulk, fmt.Sprintf("file-%03d.txt", index)), nil, 0o644); err != nil {
			return err
		}
	}
	anonymous := api.New(fixtures.BackendOf(t.Env).URL, t.Recorder)
	for _, route := range []string{"/download-manifest", "/delete-batch"} {
		if err = anonymous.JSON(ctx, "POST", base+route, map[string]any{"paths": []string{"selected"}}, nil, 401); err != nil {
			return err
		}
	}
	if err = t.Step("one complete manifest preserves more than 200 entries, same-named files and empty directories", func() error {
		actual := map[string]string{}
		var manifest downloadManifest
		if err := c.JSON(ctx, "POST", base+"/download-manifest", map[string]any{"paths": []string{"selected", "selected/a/same.txt"}}, &manifest, 200); err != nil {
			return err
		}
		if len(manifest.Errors) != 0 || manifest.Generation <= 0 {
			return fmt.Errorf("invalid complete manifest %+v", manifest)
		}
		for _, entry := range manifest.Entries {
			if _, duplicate := actual[entry.Path]; duplicate {
				return fmt.Errorf("duplicate manifest path %s", entry.Path)
			}
			actual[entry.Path] = entry.Type
			if content, selected := contents[entry.Path]; entry.Type == "file" && selected {
				response, err := c.Do(ctx, "GET", base+"/download?path="+url.QueryEscape(entry.Path)+fmt.Sprintf("&expected_generation=%d", manifest.Generation), nil, nil)
				if err != nil {
					return err
				}
				if err = c.Expect(response, 200); err != nil {
					return err
				}
				if string(response.Body) != content || int64(len(response.Body)) != entry.Size {
					return fmt.Errorf("download differs from manifest for %s", entry.Path)
				}
			} else if entry.Type == "file" && entry.Size != 0 {
				return fmt.Errorf("empty fixture has unexpected size: %+v", entry)
			}
		}
		expected := map[string]string{"selected": "directory", "selected/a": "directory", "selected/b": "directory", "selected/empty": "directory", "selected/a/same.txt": "file", "selected/b/same.txt": "file"}
		expected["selected/bulk"] = "directory"
		for index := 0; index < 240; index++ {
			expected[fmt.Sprintf("selected/bulk/file-%03d.txt", index)] = "file"
		}
		if !reflect.DeepEqual(actual, expected) {
			return fmt.Errorf("manifest scope=%v expected=%v", actual, expected)
		}
		return nil
	}); err != nil {
		return err
	}
	if err = os.Symlink("..", filepath.Join(t.Env.Dir, "servers", id, "data", "escape")); err != nil {
		return err
	}
	for _, invalid := range []string{"/", "../docker-compose.yml", "escape/docker-compose.yml"} {
		if err = c.JSON(ctx, "POST", base+"/delete-batch", map[string]any{"paths": []string{"selected", invalid}}, nil, 400); err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, c, id, "/selected/a/same.txt", "first"); err != nil {
			return err
		}
	}
	for _, invalid := range []string{"../docker-compose.yml", "escape/docker-compose.yml"} {
		if err = c.JSON(ctx, "POST", base+"/download-manifest", map[string]any{"paths": []string{invalid}}, nil, 400); err != nil {
			return err
		}
	}
	if err = c.JSON(ctx, "GET", base+"/download?path=selected/a/same.txt&expected_generation=0", nil, nil, 409); err != nil {
		return err
	}
	return t.Step("one accepted deletion task removes only deduplicated selected scopes", func() error {
		var result struct {
			Deleted int `json:"deleted"`
			Failed  int `json:"failed"`
			Pending int `json:"pending"`
			Results []struct {
				Path   string `json:"path"`
				Status string `json:"status"`
			} `json:"results"`
		}
		if err := c.RunTask(ctx, "POST", base+"/delete-batch", map[string]any{"paths": []string{"selected/a/same.txt", "selected", "selected"}}, &result); err != nil {
			return err
		}
		if result.Deleted != 1 || result.Failed != 0 || result.Pending != 0 || len(result.Results) != 1 || result.Results[0].Path != "selected" || result.Results[0].Status != "deleted" {
			return fmt.Errorf("unexpected batch deletion outcome %+v", result)
		}
		if err := c.JSON(ctx, "GET", base+"/content?path=selected/a/same.txt", nil, nil, 404); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, c, id, "/unselected.txt", "untouched")
	})
}
