package files

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func directories(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id + "/files"
	if err = c.JSON(ctx, "GET", base+"?path=/", nil, nil, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", base+"/create", map[string]string{"name": "nested", "path": "/", "type": "directory"}, nil, 200); err != nil {
		return err
	}
	for file, data := range map[string]string{"/nested/TOP.txt": "top", "/nested/deeper/small.txt": "a", "/nested/deeper/large.txt": strings.Repeat("z", 100), "/nested/deeper/comma,name.txt": "comma"} {
		if err = fixtures.CreateFile(ctx, c, id, file, data); err != nil {
			return err
		}
	}
	for _, query := range []struct {
		values map[string]any
		count  int
	}{
		{map[string]any{"regex": "\\.txt$", "search_subfolders": false}, 1},
		{map[string]any{"regex": "top", "ignore_case": false}, 0},
		{map[string]any{"regex": "top", "ignore_case": true}, 1},
		{map[string]any{"regex": "\\.txt$", "min_size": 50}, 1},
		{map[string]any{"regex": "\\.txt$", "max_size": 2}, 1},
		{map[string]any{"regex": "comma,name"}, 1},
		{map[string]any{"regex": "\\.txt$", "newer_than": "2000-01-01T00:00:00Z", "older_than": "2100-01-01T00:00:00Z"}, 4},
	} {
		var result struct {
			Count int `json:"total_count"`
		}
		if err = c.JSON(ctx, "POST", base+"/search?path=/nested", query.values, &result, 200); err != nil {
			return err
		}
		if result.Count != query.count {
			return fmt.Errorf("search %+v: count=%d expected=%d", query.values, result.Count, query.count)
		}
	}
	for _, op := range []struct {
		method, route string
		body          any
		status        int
	}{
		{"POST", "/create", map[string]string{"name": "nested", "path": "/", "type": "directory"}, 409},
		{"GET", "/content?path=/nested", nil, 400}, {"GET", "/download?path=/nested", nil, 400},
		{"POST", "/content?path=/missing", map[string]string{"content": "x"}, 404},
		{"POST", "/rename", map[string]string{"old_path": "/missing", "new_name": "new"}, 404},
		{"POST", "/rename", map[string]string{"old_path": "/nested/deeper/small.txt", "new_name": "large.txt"}, 409},
		{"POST", "/search?path=/missing", map[string]string{"regex": ".*"}, 404},
		{"POST", "/search?path=/nested/TOP.txt", map[string]string{"regex": ".*"}, 400},
		{"POST", "/search", map[string]any{"regex": ".*", "min_size": -1}, 422},
		{"POST", "/rename", map[string]string{"old_path": "/nested", "new_name": "renamed"}, 200},
	} {
		if err = c.JSON(ctx, op.method, base+op.route, op.body, nil, op.status); err != nil {
			return err
		}
	}
	if err = fixtures.CheckFile(ctx, c, id, "/renamed/deeper/large.txt", strings.Repeat("z", 100)); err != nil {
		return err
	}
	if err = c.JSON(ctx, "DELETE", base+"?path=/renamed", nil, nil, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", base+"/content?path=/renamed/TOP.txt", nil, nil, 404); err != nil {
		return err
	}
	if err = c.JSON(ctx, "DELETE", base+"?path=/renamed", nil, nil, 404); err != nil {
		return err
	}
	return t.Step("Linux filenames preserve literal backslashes through CRUD", func() error {
		original := `config\notes.txt`
		renamed := `config\renamed.txt`
		if err := fixtures.CreateFile(ctx, c, id, "/"+original, "literal filename"); err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", base+"/rename", map[string]string{"old_path": original, "new_name": renamed}, nil, 200); err != nil {
			return err
		}
		if err := fixtures.CheckFile(ctx, c, id, renamed, "literal filename"); err != nil {
			return err
		}
		if err := c.JSON(ctx, "GET", base+"/content?path="+url.QueryEscape(original), nil, nil, 404); err != nil {
			return err
		}
		if err := c.JSON(ctx, "DELETE", base+"?path="+url.QueryEscape(renamed), nil, nil, 200); err != nil {
			return err
		}
		return c.JSON(ctx, "GET", base+"/content?path="+url.QueryEscape(renamed), nil, nil, 404)
	})
}

func upload(ctx context.Context, c *api.Client, route string, files map[string]string, status int) (map[string]map[string]any, error) {
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	for name, content := range files {
		part, err := form.CreateFormFile("files", name)
		if err != nil {
			return nil, err
		}
		if _, err = part.Write([]byte(content)); err != nil {
			return nil, err
		}
	}
	if err := form.Close(); err != nil {
		return nil, err
	}
	response, err := c.Do(ctx, "POST", route, body.Bytes(), http.Header{"Content-Type": {form.FormDataContentType()}})
	if err != nil {
		return nil, err
	}
	if err = c.Expect(response, status); err != nil {
		return nil, err
	}
	var result struct {
		Results map[string]map[string]any `json:"results"`
	}
	if status == 200 {
		err = json.Unmarshal(response.Body, &result)
	}
	return result.Results, err
}

func multipartPolicies(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id + "/files"
	for _, file := range []string{"a.txt", "b.txt"} {
		if err = fixtures.CreateFile(ctx, c, id, "/"+file, "original"); err != nil {
			return err
		}
	}
	for _, mode := range []string{"never_overwrite", "always_overwrite", "per_file"} {
		var session struct {
			ID        string           `json:"session_id"`
			Conflicts []map[string]any `json:"conflicts"`
		}
		structure := []map[string]any{{"path": "a.txt", "name": "a.txt", "type": "file", "size": 3}, {"path": "b.txt", "name": "b.txt", "type": "file", "size": 3}, {"path": "nested/new.txt", "name": "new.txt", "type": "file", "size": 3}}
		if err = c.JSON(ctx, "POST", base+"/upload/check?path=/", map[string]any{"files": structure}, &session, 200); err != nil {
			return err
		}
		if len(session.Conflicts) < 2 {
			return fmt.Errorf("missing upload conflicts")
		}
		route := base + "/upload/multiple?path=/&session_id=" + session.ID
		if _, err = upload(ctx, c, route, map[string]string{"a.txt": "new"}, 400); err != nil {
			return err
		}
		policy := map[string]any{"mode": mode}
		if mode == "per_file" {
			if err = c.JSON(ctx, "POST", base+"/upload/policy?session_id="+session.ID, policy, nil, 400); err != nil {
				return err
			}
			decisions := []map[string]any{}
			for _, conflict := range session.Conflicts {
				decisions = append(decisions, map[string]any{"path": conflict["path"], "overwrite": conflict["path"] == "a.txt"})
			}
			policy["decisions"] = decisions
		}
		if err = c.JSON(ctx, "POST", base+"/upload/policy?session_id="+session.ID, policy, nil, 200); err != nil {
			return err
		}
		result, err := upload(ctx, c, route, map[string]string{"a.txt": mode, "b.txt": mode, "nested/new.txt": mode}, 200)
		if err != nil {
			return err
		}
		expectA, expectB := mode, mode
		if mode == "never_overwrite" {
			expectA, expectB = "original", "original"
		}
		if mode == "per_file" {
			expectB = "always_overwrite"
		}
		if err = fixtures.CheckFile(ctx, c, id, "/a.txt", expectA); err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, c, id, "/b.txt", expectB); err != nil {
			return err
		}
		if len(result) != 3 {
			return fmt.Errorf("multipart result count=%d", len(result))
		}
		if _, err = upload(ctx, c, route, map[string]string{"a.txt": "consumed"}, 404); err != nil {
			return err
		}
	}
	var session struct {
		ID string `json:"session_id"`
	}
	if err = c.JSON(ctx, "POST", base+"/upload/check?path=/", map[string]any{"files": []any{}}, &session, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", base+"/upload/policy?reusable=true&session_id="+session.ID, map[string]string{"mode": "always_overwrite"}, nil, 200); err != nil {
		return err
	}
	for _, content := range []string{"first", "second"} {
		if _, err = upload(ctx, c, base+"/upload/multiple?path=/&session_id="+session.ID, map[string]string{"reusable.txt": content}, 200); err != nil {
			return err
		}
	}
	if err = fixtures.CheckFile(ctx, c, id, "/reusable.txt", "second"); err != nil {
		return err
	}
	return c.JSON(ctx, "POST", base+"/upload/policy?session_id=missing", map[string]string{"mode": "always_overwrite"}, nil, 404)
}

func confinement(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id + "/files"
	if err = os.Symlink("..", filepath.Join(t.Env.Dir, "servers", id, "data", "outside")); err != nil {
		return err
	}
	for _, op := range []struct {
		method, route string
		body          any
	}{
		{"GET", "/content?path=" + url.QueryEscape("../docker-compose.yml"), nil},
		{"GET", "/content?path=/outside/docker-compose.yml", nil},
		{"GET", "/download?path=" + url.QueryEscape("../docker-compose.yml"), nil},
		{"GET", "?path=..", nil},
		{"POST", "/search?path=..", map[string]string{"regex": "docker-compose"}},
		{"POST", "/create", map[string]string{"name": "../escape.txt", "type": "file", "path": "/"}},
		{"POST", "/content?path=../escape.txt", map[string]string{"content": "escape"}},
		{"DELETE", "?path=../escape.txt", nil},
		{"POST", "/upload/check?path=..", map[string]any{"files": []any{}}},
	} {
		if err = c.JSON(ctx, op.method, base+op.route, op.body, nil, 400); err != nil {
			return err
		}
	}
	if err = fixtures.CreateFile(ctx, c, id, "/safe.txt", "safe"); err != nil {
		return err
	}
	if err = os.Symlink("missing-target", filepath.Join(t.Env.Dir, "servers", id, "data", "broken")); err != nil {
		return err
	}
	var listing struct {
		Items []struct {
			Name string `json:"name"`
		} `json:"items"`
	}
	if err = c.JSON(ctx, "GET", base+"?path=/", nil, &listing, 200); err != nil {
		return err
	}
	foundSafe := false
	for _, item := range listing.Items {
		if item.Name == "broken" {
			return fmt.Errorf("unreadable directory entry should be omitted")
		}
		foundSafe = foundSafe || item.Name == "safe.txt"
	}
	if !foundSafe {
		return fmt.Errorf("broken symlink hid the normal file from the listing")
	}
	if err = c.JSON(ctx, "POST", base+"/rename", map[string]string{"old_path": "/safe.txt", "new_name": "../escape.txt"}, nil, 400); err != nil {
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
	if _, err = upload(ctx, c, base+"/upload/multiple?path=/&session_id="+session.ID, map[string]string{"not-written.txt": "safe", "../escape.txt": "escape"}, 400); err != nil {
		return err
	}
	if err = c.JSON(ctx, "GET", base+"/content?path=/not-written.txt", nil, nil, 404); err != nil {
		return err
	}
	return fixtures.CheckFile(ctx, c, id, "/safe.txt", "safe")
}
