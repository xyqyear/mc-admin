package api

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type terminalError struct{ error }

func Permanent(err error) error { return terminalError{err} }

func Wait(ctx context.Context, interval time.Duration, description string, probe func(context.Context) (bool, error)) error {
	var last error
	for {
		if err := ctx.Err(); err != nil {
			return fmt.Errorf("waiting for %s: %w (last observation: %v)", description, err, last)
		}
		ready, err := probe(ctx)
		var terminal terminalError
		if errors.As(err, &terminal) {
			return fmt.Errorf("waiting for %s: %w", description, terminal.error)
		}
		if err == nil && ready {
			return nil
		}
		last = err
		timer := time.NewTimer(interval)
		select {
		case <-ctx.Done():
			timer.Stop()
		case <-timer.C:
		}
	}
}

func (c *Client) SSE(ctx context.Context, method, path string, input any, terminal string) (map[string]any, error) {
	return c.SSEEvents(ctx, method, path, input, terminal, nil)
}

func (c *Client) SSEEvents(ctx context.Context, method, path string, input any, terminal string, observe func(map[string]any) error) (map[string]any, error) {
	var body []byte
	var err error
	if input != nil {
		body, err = json.Marshal(input)
		if err != nil {
			return nil, err
		}
	}
	response, err := c.request(ctx, method, path, body, http.Header{"Content-Type": {"application/json"}, "Accept": {"text/event-stream"}})
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	c.Recorder.Event("sse_open", map[string]any{"method": method, "path": path, "status": response.StatusCode, "request": input})
	if response.StatusCode != 200 {
		data, _ := io.ReadAll(io.LimitReader(response.Body, 2048))
		return nil, c.Expect(Response{Status: response.StatusCode, Body: data}, 200)
	}
	if contentType(response.Header) != "text/event-stream" {
		return nil, fmt.Errorf("%s returned %q instead of SSE", path, response.Header.Get("Content-Type"))
	}
	return ReadSSE(response.Body, func(event map[string]any) (bool, error) {
		c.Recorder.Event("sse_event", map[string]any{"path": path, "event": event})
		kind := event["event_type"]
		if kind == nil {
			kind = event["type"]
		}
		if kind == nil {
			kind = event["stage"]
		}
		if kind == "error" || event["phase"] == "error" {
			return false, fmt.Errorf("SSE error: %v", event["message"])
		}
		if observe != nil {
			if err := observe(event); err != nil {
				return false, err
			}
		}
		return kind == terminal, nil
	})
}

func ReadSSE(reader io.Reader, accept func(map[string]any) (bool, error)) (map[string]any, error) {
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 4096), 1<<20)
	var lines []string
	size := 0
	for scanner.Scan() {
		line := scanner.Text()
		if line == "" {
			if len(lines) == 0 {
				continue
			}
			var event map[string]any
			if err := json.Unmarshal([]byte(strings.Join(lines, "\n")), &event); err != nil {
				return nil, fmt.Errorf("invalid SSE JSON: %w", err)
			}
			lines = nil
			size = 0
			done, err := accept(event)
			if err != nil || done {
				return event, err
			}
		} else if strings.HasPrefix(line, "data:") {
			value := strings.TrimPrefix(line, "data:")
			value = strings.TrimPrefix(value, " ")
			size += len(value)
			if size > 1<<20 {
				return nil, fmt.Errorf("SSE event exceeds 1 MiB")
			}
			lines = append(lines, value)
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return nil, fmt.Errorf("SSE ended before its required terminal event")
}

type Task struct {
	ID     string         `json:"task_id"`
	Status string         `json:"status"`
	Error  string         `json:"error"`
	Result map[string]any `json:"result"`
}

func (c *Client) Task(ctx context.Context, id string) (Task, error) {
	var task Task
	err := Wait(ctx, 200*time.Millisecond, "task "+id, func(ctx context.Context) (bool, error) {
		if err := c.JSON(ctx, "GET", "/api/tasks/"+id, nil, &task, 200); err != nil {
			return false, Permanent(err)
		}
		switch strings.ToLower(task.Status) {
		case "completed", "failed", "cancelled":
			return true, nil
		}
		return false, fmt.Errorf("status=%s", task.Status)
	})
	if err != nil {
		return task, err
	}
	if strings.ToLower(task.Status) != "completed" {
		return task, fmt.Errorf("task %s ended %s: %s", id, task.Status, task.Error)
	}
	return task, nil
}
