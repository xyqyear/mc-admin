package files

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "files.content-search-and-task", Suite: "files", Tags: []string{"smoke"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: content},
		{ID: "files.directories-search-and-errors", Suite: "files", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: directories},
		{ID: "files.multipart-policies", Suite: "files", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: multipartPolicies},
		{ID: "files.path-confinement", Suite: "files", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: confinement},
	}
}

func content(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	base := "/api/servers/" + id + "/files"
	if err = t.Step("create, write and read a UTF-8 file", func() error {
		if err := fixtures.CreateFile(ctx, client, id, "/smoke.txt", "Minecraft 冒烟测试\n"); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/smoke.txt", "Minecraft 冒烟测试\n")
	}); err != nil {
		return err
	}
	if err = t.Step("search uses the deployed fd binary", func() error {
		var found struct {
			Count int `json:"total_count"`
		}
		if err := client.JSON(ctx, "POST", base+"/search", map[string]any{"regex": "^smoke\\.txt$"}, &found, 200); err != nil {
			return err
		}
		if found.Count != 1 {
			return fmt.Errorf("search found %d files, expected 1", found.Count)
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("ownership repair reaches a successful task terminal state", func() error {
		var response struct {
			ID string `json:"task_id"`
		}
		if err := client.JSON(ctx, "POST", base+"/ownership/restore", nil, &response, 200); err != nil {
			return err
		}
		_, err := client.Task(ctx, response.ID)
		return err
	}); err != nil {
		return err
	}
	return t.Step("rename, download and delete preserve observable file behavior", func() error {
		if err := client.JSON(ctx, "POST", base+"/rename", map[string]string{"old_path": "/smoke.txt", "new_name": "renamed.txt"}, nil, 200); err != nil {
			return err
		}
		response, err := client.Do(ctx, "GET", base+"/download?path=/renamed.txt", nil, nil)
		if err != nil {
			return err
		}
		if err = client.Expect(response, 200); err != nil {
			return err
		}
		if string(response.Body) != "Minecraft 冒烟测试\n" {
			return fmt.Errorf("download content mismatch")
		}
		if err = client.JSON(ctx, "DELETE", base+"?path=/renamed.txt", nil, nil, 200); err != nil {
			return err
		}
		return client.JSON(ctx, "GET", base+"/content?path=/renamed.txt", nil, nil, 404)
	})
}
