package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/coder/websocket"
)

func (c *Client) OpenWebSocket(ctx context.Context, path string) (*websocket.Conn, error) {
	if !strings.HasPrefix(path, "/") || strings.HasPrefix(path, "//") {
		return nil, fmt.Errorf("WebSocket path must be relative")
	}
	headers := http.Header{"Origin": {c.URL()}}
	if c.Bearer != "" {
		headers.Set("Authorization", "Bearer "+c.Bearer)
	}
	connection, response, err := websocket.Dial(ctx, c.URL()+path, &websocket.DialOptions{HTTPClient: c.HTTP, HTTPHeader: headers})
	status := 0
	if response != nil {
		status = response.StatusCode
	}
	c.Recorder.Event("websocket_open", map[string]any{"path": path, "status": status})
	if err != nil {
		return nil, err
	}
	connection.SetReadLimit(1 << 20)
	return connection, nil
}

func (c *Client) WebSocket(ctx context.Context, path string, accept func(map[string]any) (bool, error)) error {
	connection, err := c.OpenWebSocket(ctx, path)
	if err != nil {
		return err
	}
	defer connection.CloseNow()
	for {
		kind, data, err := connection.Read(ctx)
		if err != nil {
			return err
		}
		if kind != websocket.MessageText {
			return fmt.Errorf("expected a WebSocket text frame")
		}
		var event map[string]any
		if err = json.Unmarshal(data, &event); err != nil {
			return err
		}
		c.Recorder.Event("websocket_event", map[string]any{"path": path, "event": event})
		done, err := accept(event)
		if done || err != nil {
			return err
		}
	}
}
