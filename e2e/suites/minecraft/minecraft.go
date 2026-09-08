package minecraft

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "minecraft.lifecycle", Suite: "minecraft", Tags: []string{"smoke", "minecraft"}, Recipe: recipes.Lifecycle, Isolation: engine.Fresh, Timeout: 8 * time.Minute, Run: lifecycle},
		{ID: "minecraft.overview", Suite: "minecraft", Tags: []string{"smoke", "minecraft"}, Recipe: recipes.Running, Isolation: engine.ObserveReuse, Timeout: time.Minute, Run: overview},
		{ID: "minecraft.rcon-and-files", Suite: "minecraft", Tags: []string{"smoke", "minecraft"}, Recipe: recipes.Running, Isolation: engine.ObserveReuse, Timeout: time.Minute, Run: observe},
		{ID: "minecraft.console-and-runtime-controls", Suite: "minecraft", Tags: []string{"regression", "minecraft"}, Recipe: recipes.Running, Isolation: engine.Fresh, Timeout: 6 * time.Minute, Run: consoleAndControls},
		{ID: "minecraft.stopped-and-invalid-requests", Suite: "minecraft", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: time.Minute, Run: negativeRequests},
		{ID: "minecraft.scheduled-restart", Suite: "minecraft", Tags: []string{"regression", "minecraft"}, Recipe: recipes.Running, Isolation: engine.Fresh, Timeout: 4 * time.Minute, Run: scheduledRestart},
	}
}

func lifecycle(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	id := server.ID
	if err = t.Step("Compose accepts a label whose value contains equals signs", func() error {
		compose := strings.Replace(server.Compose, "    labels:\n", "    labels:\n      io.mc-admin.e2e.lifecycle: 'phase=ready=healthy'\n", 1)
		var task struct {
			ID string `json:"task_id"`
		}
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/compose", map[string]string{"yaml_content": compose}, &task, 200); err != nil {
			return err
		}
		_, err := client.Task(ctx, task.ID)
		return err
	}); err != nil {
		return err
	}
	if err = t.Step("stopped server rejects RCON and up starts a real Minecraft process", func() error {
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/rcon", map[string]string{"command": "list"}, nil, 409); err != nil {
			return err
		}
		if err := fixtures.Operation(ctx, client, id, "up"); err != nil {
			return err
		}
		return fixtures.WaitStatus(ctx, client, id, "healthy")
	}); err != nil {
		return err
	}
	if err = t.Step("RCON mutates and reads real game state; running deletion is refused", func() error {
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/rcon", map[string]string{"command": "whitelist add e2eprobe"}, nil, 200); err != nil {
			return err
		}
		var output struct {
			Output string `json:"output"`
		}
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/rcon", map[string]string{"command": "whitelist list"}, &output, 200); err != nil {
			return err
		}
		if !strings.Contains(output.Output, "e2eprobe") {
			return fmt.Errorf("RCON mutation missing: %s", output.Output)
		}
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/message", map[string]string{"message": "E2E 消息 \"quoted\"", "color": "green"}, nil, 204); err != nil {
			return err
		}
		return client.JSON(ctx, "POST", "/api/servers/"+id+"/operations", map[string]string{"action": "remove"}, nil, 409)
	}); err != nil {
		return err
	}
	if err = t.Step("restart returns to a healthy game server", func() error {
		if err := fixtures.Operation(ctx, client, id, "restart"); err != nil {
			return err
		}
		return fixtures.WaitStatus(ctx, client, id, "healthy")
	}); err != nil {
		return err
	}
	if err = t.Step("stopped container accepts configuration rebuild and stays stopped", func() error {
		if err := fixtures.Operation(ctx, client, id, "stop"); err != nil {
			return err
		}
		if err := fixtures.WaitStatus(ctx, client, id, "created"); err != nil {
			return err
		}
		var task struct {
			ID string `json:"task_id"`
		}
		changed := strings.Replace(server.Compose, "MAX_MEMORY: 1G", "MAX_MEMORY: 768M", 1)
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/compose", map[string]string{"yaml_content": changed}, &task, 200); err != nil {
			return err
		}
		if _, err := client.Task(ctx, task.ID); err != nil {
			return err
		}
		if err := fixtures.Status(ctx, client, id, "exists"); err != nil {
			return err
		}
		var compose struct {
			YAML string `json:"yaml_content"`
		}
		if err := client.JSON(ctx, "GET", "/api/servers/"+id+"/compose", nil, &compose, 200); err != nil {
			return err
		}
		if compose.YAML != changed {
			return fmt.Errorf("stopped rebuild did not save the requested compose")
		}
		if err := fixtures.Operation(ctx, client, id, "up"); err != nil {
			return err
		}
		return fixtures.WaitStatus(ctx, client, id, "healthy")
	}); err != nil {
		return err
	}
	return t.Step("stop, down and remove complete the server lifecycle", func() error {
		if err := fixtures.Operation(ctx, client, id, "stop"); err != nil {
			return err
		}
		if err := fixtures.WaitStatus(ctx, client, id, "created"); err != nil {
			return err
		}
		if err := fixtures.Operation(ctx, client, id, "down"); err != nil {
			return err
		}
		if err := fixtures.Status(ctx, client, id, "exists"); err != nil {
			return err
		}
		if err := fixtures.Operation(ctx, client, id, "remove"); err != nil {
			return err
		}
		return client.JSON(ctx, "GET", "/api/servers/"+id, nil, nil, 404)
	})
}

func overview(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	return t.Step("overview and resource APIs describe the running server", func() error {
		var items []struct {
			ID     string `json:"id"`
			Status string `json:"status"`
		}
		if err := client.JSON(ctx, "GET", "/api/servers/overview", nil, &items, 200); err != nil {
			return err
		}
		if len(items) != 1 || items[0].ID != id || !strings.EqualFold(items[0].Status, "healthy") {
			return fmt.Errorf("unexpected overview: %+v", items)
		}
		for _, suffix := range []string{"/memory", "/disk-usage", "/online-players", "/world-restore/layout"} {
			if err := client.JSON(ctx, "GET", "/api/servers/"+id+suffix, nil, nil, 200); err != nil {
				return err
			}
		}
		return nil
	})
}

func observe(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	return t.Step("RCON responds and generated server properties use the fixed game target", func() error {
		var output struct {
			Output string `json:"output"`
		}
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/rcon", map[string]string{"command": "list"}, &output, 200); err != nil {
			return err
		}
		if output.Output == "" {
			return fmt.Errorf("empty RCON response")
		}
		var file struct {
			Content string `json:"content"`
		}
		if err := client.JSON(ctx, "GET", "/api/servers/"+id+"/files/content?path=/server.properties", nil, &file, 200); err != nil {
			return err
		}
		if !strings.Contains(file.Content, "server-port=25565") {
			return fmt.Errorf("incorrect generated game port")
		}
		return nil
	})
}
