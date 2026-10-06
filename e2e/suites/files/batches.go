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

type manifestPage struct {
	Generation int             `json:"server_generation"`
	Entries    []manifestEntry `json:"entries"`
	Errors     []struct {
		Path string `json:"path"`
	} `json:"errors"`
	Cursor string `json:"next_cursor"`
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
	anonymous := api.New(fixtures.BackendOf(t.Env).URL, t.Recorder)
	for _, route := range []string{"/download-manifest", "/delete-batch"} {
		if err = anonymous.JSON(ctx, "POST", base+route, map[string]any{"paths": []string{"selected"}}, nil, 401); err != nil {
			return err
		}
	}
	if err = t.Step("recursive pages preserve same-named files and empty directories without expanding scope", func() error {
		cursor := ""
		actual := map[string]string{}
		for pageNumber := 0; pageNumber < 10; pageNumber++ {
			request := map[string]any{"paths": []string{"selected", "selected/a/same.txt"}, "limit": 2}
			if cursor != "" {
				request["cursor"] = cursor
			}
			var page manifestPage
			if err := c.JSON(ctx, "POST", base+"/download-manifest", request, &page, 200); err != nil {
				return err
			}
			if len(page.Entries)+len(page.Errors) > 2 || len(page.Errors) != 0 || page.Generation <= 0 {
				return fmt.Errorf("invalid bounded manifest page %+v", page)
			}
			for _, entry := range page.Entries {
				if _, duplicate := actual[entry.Path]; duplicate {
					return fmt.Errorf("duplicate manifest path %s", entry.Path)
				}
				actual[entry.Path] = entry.Type
				if entry.Type == "file" {
					response, err := c.Do(ctx, "GET", base+"/download?path="+url.QueryEscape(entry.Path)+fmt.Sprintf("&expected_generation=%d", page.Generation), nil, nil)
					if err != nil {
						return err
					}
					if err = c.Expect(response, 200); err != nil {
						return err
					}
					if string(response.Body) != contents[entry.Path] || int64(len(response.Body)) != entry.Size {
						return fmt.Errorf("download differs from manifest for %s", entry.Path)
					}
				}
			}
			cursor = page.Cursor
			if cursor == "" {
				break
			}
		}
		expected := map[string]string{"selected": "directory", "selected/a": "directory", "selected/b": "directory", "selected/empty": "directory", "selected/a/same.txt": "file", "selected/b/same.txt": "file"}
		if cursor != "" || !reflect.DeepEqual(actual, expected) {
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
