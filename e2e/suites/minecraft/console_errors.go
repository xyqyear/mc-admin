package minecraft

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/coder/websocket"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func consoleSafeAdapterErrors(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	s := fixtures.ServerOf(t.Env)
	base := "/api/servers/" + s.ID
	var original struct {
		YAML    string `json:"yaml_content"`
		Version string `json:"version"`
	}
	if err = c.JSON(ctx, "GET", base+"/compose", nil, &original, 200); err != nil {
		return err
	}
	changed := strings.Replace(original.YAML, "    labels:\n", "    logging:\n      driver: none\n    labels:\n", 1)
	if changed == original.YAML {
		return fmt.Errorf("owned compose fixture has no service label anchor")
	}
	var accepted struct {
		ID string `json:"task_id"`
	}
	if err = c.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": changed, "version": original.Version}, &accepted, 200); err != nil {
		return err
	}
	if _, err = c.Task(ctx, accepted.ID); err != nil {
		return err
	}
	if err = fixtures.WaitStatus(ctx, c, s.ID, "healthy"); err != nil {
		return err
	}
	connection, err := c.OpenWebSocket(ctx, base+"/console?cols=80&rows=24")
	if err != nil {
		return err
	}
	defer connection.CloseNow()
	kind, data, err := connection.Read(ctx)
	if err != nil {
		return err
	}
	var event map[string]any
	if kind != websocket.MessageText {
		return fmt.Errorf("console failure frame is not text")
	}
	if err = json.Unmarshal(data, &event); err != nil {
		return err
	}
	if len(event) != 2 || event["type"] != "error" || event["message"] != "获取历史日志失败，请重试" {
		return fmt.Errorf("unsupported Docker log history did not produce the safe console error")
	}
	if err = connection.Write(ctx, websocket.MessageText, []byte(`{"type":"input","data":"whitelist add safeconsoleprobe\n"}`)); err != nil {
		return err
	}
	if err = api.Wait(ctx, 250*time.Millisecond, "stdin remains usable after history failure", func(ctx context.Context) (bool, error) {
		var result struct {
			Output string `json:"output"`
		}
		if err := c.JSON(ctx, "POST", base+"/rcon", map[string]string{"command": "whitelist list"}, &result, 200); err != nil {
			return false, api.Permanent(err)
		}
		return strings.Contains(result.Output, "safeconsoleprobe"), nil
	}); err != nil {
		return err
	}
	if err = connection.Close(websocket.StatusNormalClosure, "owned console test complete"); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", base+"/rcon", map[string]string{"command": "whitelist remove safeconsoleprobe"}, nil, 200); err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	logs, err := backend.Docker.Run(ctx, "logs", backend.Name)
	if err != nil {
		return err
	}
	if !strings.Contains(logs, "Cannot read console history: APIError") || strings.Contains(logs, "configured logging driver does not support reading") || strings.Contains(logs, "Client Error for http+docker") {
		return fmt.Errorf("Docker history error logs lack safe diagnostics or expose adapter response text")
	}
	return fixtures.Status(ctx, c, s.ID, "healthy")
}
