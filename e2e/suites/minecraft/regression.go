package minecraft

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/coder/websocket"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func negativeRequests(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	base := "/api/servers/" + fixtures.ServerOf(t.Env).ID
	for _, suffix := range []string{"/cpu_percent", "/memory", "/iostats"} {
		if err = c.JSON(ctx, "GET", base+suffix, nil, nil, 409); err != nil {
			return err
		}
	}
	for _, op := range []struct {
		route  string
		body   any
		status int
	}{
		{"/rcon", map[string]string{"command": ""}, 422}, {"/rcon", map[string]string{"command": strings.Repeat("x", 1001)}, 422},
		{"/rcon", map[string]string{"command": "list"}, 409}, {"/message", map[string]string{"message": "hello"}, 409},
		{"/message", map[string]string{"message": ""}, 422}, {"/message", map[string]string{"message": "hello", "color": "invalid"}, 422},
		{"/message", map[string]string{"message": "hello", "target_player": "@a"}, 422}, {"/message", map[string]string{"message": strings.Repeat("x", 2001)}, 422},
		{"/operations", map[string]string{"action": "invalid"}, 400},
	} {
		if err = c.JSON(ctx, "POST", base+op.route, op.body, nil, op.status); err != nil {
			return err
		}
	}
	for _, suffix := range []string{"", "/compose", "/disk-usage"} {
		if err = c.JSON(ctx, "GET", "/api/servers/missing"+suffix, nil, nil, 404); err != nil {
			return err
		}
	}
	if err = c.JSON(ctx, "POST", "/api/servers/missing/rcon", map[string]string{"command": "list"}, nil, 404); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", "/api/servers/missing/message", map[string]string{"message": "hi"}, nil, 404); err != nil {
		return err
	}
	return c.WebSocket(ctx, base+"/console?cols=80&rows=24", func(event map[string]any) (bool, error) {
		if event["type"] != "error" || !strings.Contains(fmt.Sprint(event["message"]), "未运行") {
			return false, fmt.Errorf("stopped console returned unexpected event: %+v", event)
		}
		return true, nil
	})
}

func consoleAndControls(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	s := fixtures.ServerOf(t.Env)
	base := "/api/servers/" + s.ID
	if err = t.Step("runtime counters describe the real Minecraft container", func() error {
		for _, suffix := range []string{"/cpu_percent", "/memory", "/iostats", "/disk-usage"} {
			var values map[string]float64
			if err := c.JSON(ctx, "GET", base+suffix, nil, &values, 200); err != nil {
				return err
			}
			for name, value := range values {
				if value < 0 {
					return fmt.Errorf("negative metric %s=%f", name, value)
				}
			}
			if suffix == "/memory" && values["memoryUsageBytes"] <= 0 {
				return fmt.Errorf("running JVM has no memory usage")
			}
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("console streams logs, accepts resize and executes stdin commands", func() error {
		path := base + "/console?cols=80&rows=24"
		conn, err := c.OpenWebSocket(ctx, path)
		if err != nil {
			return err
		}
		defer conn.CloseNow()
		read := func() (map[string]any, error) {
			kind, data, err := conn.Read(ctx)
			if err != nil {
				return nil, err
			}
			if kind != websocket.MessageText {
				return nil, fmt.Errorf("console frame is not text")
			}
			var event map[string]any
			err = json.Unmarshal(data, &event)
			t.Env.Recorder.Event("console_event", map[string]any{"event": event})
			return event, err
		}
		event, err := read()
		if err != nil {
			return err
		}
		if event["type"] != "log" || !strings.Contains(fmt.Sprint(event["content"]), "Done") {
			return fmt.Errorf("console history did not include game readiness")
		}
		for _, message := range []string{`{"type":"resize","width":120,"height":40}`, `{"type":"input","data":"whitelist add consoleprobe\n"}`, `{"type":"unknown"}`} {
			if err = conn.Write(ctx, websocket.MessageText, []byte(message)); err != nil {
				return err
			}
		}
		seenCommand, seenInvalid := false, false
		for !seenCommand || !seenInvalid {
			event, err = read()
			if err != nil {
				return err
			}
			if event["type"] == "error" {
				return fmt.Errorf("console error: %+v", event)
			}
			if strings.Contains(fmt.Sprint(event["content"]), "Added consoleprobe") {
				seenCommand = true
			}
			if strings.Contains(fmt.Sprint(event["message"]), "未知消息类型") {
				seenInvalid = true
			}
		}
		var output struct {
			Output string `json:"output"`
		}
		if err = c.JSON(ctx, "POST", base+"/rcon", map[string]string{"command": "whitelist list"}, &output, 200); err != nil {
			return err
		}
		if !strings.Contains(output.Output, "consoleprobe") {
			return fmt.Errorf("stdin command did not mutate game whitelist")
		}
		return c.JSON(ctx, "POST", base+"/rcon", map[string]string{"command": "whitelist remove consoleprobe"}, nil, 200)
	}); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", base+"/message", map[string]string{"message": "first line\n\n第二行 \"quoted\"", "target_player": "consoleprobe", "color": "gold"}, nil, 204); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", base+"/populate", map[string]string{"archive_filename": "none.zip"}, nil, 409); err != nil {
		return err
	}
	if err = fixtures.Operation(ctx, c, s.ID, "stop"); err != nil {
		return err
	}
	if err = fixtures.WaitStatus(ctx, c, s.ID, "created"); err != nil {
		return err
	}
	if err = fixtures.Operation(ctx, c, s.ID, "start"); err != nil {
		return err
	}
	if err = fixtures.WaitStatus(ctx, c, s.ID, "healthy"); err != nil {
		return err
	}
	var task struct {
		ID string `json:"task_id"`
	}
	if err = c.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": strings.Replace(s.Compose, "MAX_MEMORY: 1G", "MAX_MEMORY: 768M", 1)}, &task, 200); err != nil {
		return err
	}
	if _, err = c.Task(ctx, task.ID); err != nil {
		return err
	}
	if err = fixtures.WaitStatus(ctx, c, s.ID, "healthy"); err != nil {
		return err
	}
	var info struct {
		Memory int64 `json:"maxMemoryBytes"`
	}
	if err = c.JSON(ctx, "GET", base, nil, &info, 200); err != nil {
		return err
	}
	if info.Memory != 768*1024*1024 {
		return fmt.Errorf("running rebuild memory setting incorrect: %d", info.Memory)
	}
	return nil
}
