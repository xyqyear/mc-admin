package players

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/coder/websocket"
	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

const playerUUID = "123e4567e89b42d3a456426614174000"
const readyUUID = "123e4567e89b42d3a456426614174001"
const offlineUUID = "123e4567e89b32d3a456426614174002"

func Cases(r fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "players.tracking-events-and-history", Suite: "players", Tags: []string{"regression"}, Recipe: r.Server, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: tracking},
		{ID: "players.identity-config-and-cleanup", Suite: "players", Tags: []string{"regression"}, Recipe: r.Server, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: identity},
		{ID: "players.legacy-cleanup-and-cached-profiles", Suite: "players", Tags: []string{"regression"}, Recipe: r.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: legacy},
		{ID: "players.heartbeat-crash-recovery", Suite: "players", Tags: []string{"regression"}, Recipe: r.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: crashRecovery},
		{ID: "players.live-profile-and-skin", Suite: "players", Tags: []string{"external", "mojang"}, Recipe: r.Base, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: liveProfile},
	}
}

type detail struct {
	ID           int    `json:"player_db_id"`
	UUID         string `json:"uuid"`
	Name         string `json:"current_name"`
	Online       bool   `json:"is_online"`
	Sessions     int    `json:"total_sessions"`
	Messages     int    `json:"total_messages"`
	Achievements int    `json:"total_achievements"`
}

type logSource struct {
	client  *api.Client
	id      string
	backend *fixtures.Backend
	path    string
}

func (s *logSource) append(ctx context.Context, lines ...string) error {
	_, err := s.backend.Docker.Run(ctx, "exec", s.backend.Name, "python", "-c", "import sys; f=open(sys.argv[1], 'a', encoding='utf-8'); f.write(sys.argv[2]); f.close()", s.path, strings.Join(lines, "\n")+"\n")
	return err
}

func prepare(ctx context.Context, t *engine.Scope) (*logSource, error) {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return nil, err
	}
	id := fixtures.ServerOf(t.Env).ID
	if err = client.JSON(ctx, "POST", "/api/servers/"+id+"/files/create", map[string]string{"path": "/", "name": "logs", "type": "directory"}, nil, 200); err != nil {
		return nil, err
	}
	if err = fixtures.CreateFile(ctx, client, id, "/logs/latest.log", ""); err != nil {
		return nil, err
	}
	cache := []map[string]string{{"name": "E2EPlayer", "uuid": "123e4567-e89b-42d3-a456-426614174000"}, {"name": "ReadyFixture", "uuid": "123e4567-e89b-42d3-a456-426614174001"}, {"name": "OfflineFixture", "uuid": "123e4567-e89b-32d3-a456-426614174002"}}
	data, _ := json.Marshal(cache)
	if err = fixtures.CreateFile(ctx, client, id, "/usercache.json", string(data)); err != nil {
		return nil, err
	}
	source := &logSource{client: client, id: id, backend: fixtures.BackendOf(t.Env), path: filepath.Join(t.Env.Dir, "servers", id, "data", "logs", "latest.log")}
	err = api.Wait(ctx, 250*time.Millisecond, "real log watcher fixture readiness", func(ctx context.Context) (bool, error) {
		if err := source.append(ctx, "[12:00:00] [Server thread/INFO]: UUID of player ReadyFixture is 123e4567-e89b-42d3-a456-426614174001"); err != nil {
			return false, api.Permanent(err)
		}
		response, err := client.Do(ctx, "GET", "/api/players/uuid/"+readyUUID, nil, nil)
		if err != nil {
			return false, api.Permanent(err)
		}
		if response.Status == 404 {
			return false, nil
		}
		if err = client.Expect(response, 200); err != nil {
			return false, api.Permanent(err)
		}
		return true, nil
	})
	return source, err
}

func waitDetail(ctx context.Context, client *api.Client, uuid string, accept func(detail) bool) (detail, error) {
	var got detail
	err := api.Wait(ctx, 100*time.Millisecond, "player state "+uuid, func(ctx context.Context) (bool, error) {
		response, err := client.Do(ctx, "GET", "/api/players/uuid/"+uuid, nil, nil)
		if err != nil {
			return false, api.Permanent(err)
		}
		if response.Status == 404 {
			return false, nil
		}
		if err = client.Expect(response, 200); err != nil {
			return false, api.Permanent(err)
		}
		if err = json.Unmarshal(response.Body, &got); err != nil {
			return false, api.Permanent(err)
		}
		if accept(got) {
			return true, nil
		}
		return false, fmt.Errorf("last player state: %+v", got)
	})
	return got, err
}

func readEvent(ctx context.Context, t *engine.Scope, connection *websocket.Conn, kind string) (map[string]any, error) {
	for {
		message, data, err := connection.Read(ctx)
		if err != nil {
			return nil, err
		}
		if message != websocket.MessageText {
			return nil, fmt.Errorf("non-text public event")
		}
		var event map[string]any
		if err = json.Unmarshal(data, &event); err != nil {
			return nil, err
		}
		t.Recorder.Event("public_event", event)
		if event["type"] == kind {
			return event, nil
		}
		if event["type"] == "stream_reset" {
			return nil, fmt.Errorf("unexpected stream reset: %v", event)
		}
	}
}

func tracking(ctx context.Context, t *engine.Scope) error {
	s, err := prepare(ctx, t)
	if err != nil {
		return err
	}
	client := s.client
	connection, err := client.OpenWebSocket(ctx, "/api/events?since=0")
	if err != nil {
		return err
	}
	defer connection.CloseNow()
	if err = t.Step("real watcher commits join, chat and deduplicated achievements before publishing", func() error {
		if err := s.append(ctx, "[12:00:01] [Server thread/INFO]: UUID of player E2EPlayer is 123e4567-e89b-42d3-a456-426614174000", "[12:00:02] [Server thread/INFO]: E2EPlayer[/127.0.0.1:1234] logged in with entity id 1", "[12:00:03] [Server thread/INFO]: <E2EPlayer> first persisted chat", "[12:00:04] [Server thread/INFO]: E2EPlayer has made the advancement [Stone Age]", "[12:00:05] [Server thread/INFO]: E2EPlayer has made the advancement [Stone Age]"); err != nil {
			return err
		}
		join, err := readEvent(ctx, t, connection, "player_join")
		if err != nil {
			return err
		}
		if join["server_id"] != s.id {
			return fmt.Errorf("join event has wrong server")
		}
		return nil
	}); err != nil {
		return err
	}
	chat, err := readEvent(ctx, t, connection, "chat")
	if err != nil {
		return err
	}
	cursor, ok := chat["cursor"].(string)
	if !ok || chat["message"] != "first persisted chat" {
		return fmt.Errorf("bad committed chat event: %v", chat)
	}
	p, err := waitDetail(ctx, client, playerUUID, func(d detail) bool { return d.Online && d.Sessions == 1 && d.Messages == 1 && d.Achievements == 1 })
	if err != nil {
		return err
	}
	base := fmt.Sprintf("/api/players/%d", p.ID)
	if err = t.Step("player queries filter history and expose consistent aggregates", func() error {
		var online []detail
		if err := client.JSON(ctx, "GET", "/api/players/?online_only=true&server_id="+s.id, nil, &online, 200); err != nil {
			return err
		}
		if len(online) != 1 || online[0].ID != p.ID {
			return fmt.Errorf("incorrect online player filter")
		}
		for _, route := range []string{base + "/sessions", base + "/chat", base + "/achievements"} {
			var rows []map[string]any
			if err := client.JSON(ctx, "GET", route+"?server_id="+s.id, nil, &rows, 200); err != nil {
				return err
			}
			if len(rows) != 1 {
				return fmt.Errorf("%s returned %d records", route, len(rows))
			}
			if err := client.JSON(ctx, "GET", route+"?server_id=nonexistent-e2e-server", nil, &rows, 200); err != nil {
				return err
			}
			if len(rows) != 0 {
				return fmt.Errorf("%s ignored unknown server filter", route)
			}
		}
		for _, period := range []string{"all", "week", "month", "year"} {
			var stats map[string]any
			if err := client.JSON(ctx, "GET", base+"/sessions/stats?period="+period, nil, &stats, 200); err != nil {
				return err
			}
			if stats["total_sessions"] != float64(1) {
				return fmt.Errorf("incorrect session statistics: %v", stats)
			}
		}
		var messages []map[string]any
		if err := client.JSON(ctx, "GET", base+"/chat?search=absent", nil, &messages, 200); err != nil {
			return err
		}
		if len(messages) != 0 {
			return fmt.Errorf("chat search ignored")
		}
		for _, path := range []string{base + "/sessions?limit=0", base + "/chat?limit=501", base + "/sessions/stats?period=invalid"} {
			if err := client.JSON(ctx, "GET", path, nil, nil, 422); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		return err
	}
	if err = s.append(ctx, "[12:01:00] [Server thread/INFO]: E2EPlayer lost connection: E2E disconnect"); err != nil {
		return err
	}
	leave, err := readEvent(ctx, t, connection, "player_leave")
	if err != nil {
		return err
	}
	if leave["reason"] != "E2E disconnect" {
		return fmt.Errorf("leave reason not preserved")
	}
	if _, err = waitDetail(ctx, client, playerUUID, func(d detail) bool { return !d.Online && d.Sessions == 1 }); err != nil {
		return err
	}
	return t.Step("cursor replay returns only newer committed chat after backend restart", func() error {
		if err := s.append(ctx, "[12:01:01] [Server thread/INFO]: <E2EPlayer> second persisted chat"); err != nil {
			return err
		}
		if _, err := waitDetail(ctx, client, playerUUID, func(d detail) bool { return d.Messages == 2 }); err != nil {
			return err
		}
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		replay, err := client.OpenWebSocket(ctx, "/api/events?since="+url.QueryEscape(cursor))
		if err != nil {
			return err
		}
		defer replay.CloseNow()
		event, err := readEvent(ctx, t, replay, "chat")
		if err != nil {
			return err
		}
		next, _ := strconv.Atoi(fmt.Sprint(event["cursor"]))
		prior, _ := strconv.Atoi(cursor)
		if next <= prior || event["message"] != "second persisted chat" {
			return fmt.Errorf("cursor replay violated ordering: %v", event)
		}
		return nil
	})
}

func identity(ctx context.Context, t *engine.Scope) error {
	s, err := prepare(ctx, t)
	if err != nil {
		return err
	}
	client := s.client
	if err = s.append(ctx, "[12:00:00] [Server thread/INFO]: UUID of player E2EPlayer is 123e4567-e89b-42d3-a456-426614174000", "[12:00:01] [Server thread/INFO]: E2EPlayer[/127.0.0.1:1234] logged in with entity id 1", "[12:00:02] [Server thread/INFO]: <E2EPlayer> initial chat", "[12:00:03] [Server thread/INFO]: E2EPlayer has made the advancement [Stone Age]"); err != nil {
		return err
	}
	p, err := waitDetail(ctx, client, playerUUID, func(d detail) bool { return d.Messages == 1 && d.Achievements == 1 })
	if err != nil {
		return err
	}
	var module struct {
		Data map[string]any `json:"config_data"`
	}
	if err = client.JSON(ctx, "GET", "/api/config/modules/log_parser", nil, &module, 200); err != nil {
		return err
	}
	module.Data["chat_pattern"] = `^(E2E: )?<(\S+)> (.*)$`
	if err = client.JSON(ctx, "PUT", "/api/config/modules/log_parser", map[string]any{"config_data": module.Data}, nil, 200); err != nil {
		return err
	}
	if err = s.append(ctx, "E2E: <E2EPlayer> runtime parser configuration"); err != nil {
		return err
	}
	if _, err = waitDetail(ctx, client, playerUUID, func(d detail) bool { return d.Messages == 2 }); err != nil {
		return err
	}
	if err = t.Step("online UUID and ignored prefix gates reject real incoming log data", func() error {
		if err := s.append(ctx, "[12:00:05] [Server thread/INFO]: UUID of player OfflineFixture is 123e4567-e89b-32d3-a456-426614174002", "[12:00:06] [Server thread/INFO]: OfflineFixture[/127.0.0.1:1234] logged in with entity id 2", "[12:00:07] [Server thread/INFO]: UUID of player BoT_ignored is 123e4567-e89b-42d3-a456-426614174003", "E2E: <ReadyFixture> processing barrier"); err != nil {
			return err
		}
		if _, err := waitDetail(ctx, client, readyUUID, func(d detail) bool { return d.Messages == 1 }); err != nil {
			return err
		}
		for _, uuid := range []string{offlineUUID, "123e4567e89b42d3a456426614174003"} {
			if err := client.JSON(ctx, "GET", "/api/players/uuid/"+uuid, nil, nil, 404); err != nil {
				return err
			}
		}
		var profile map[string]any
		if err := client.JSON(ctx, "GET", "/api/players/uuid/"+offlineUUID+"/profile", nil, &profile, 200); err != nil {
			return err
		}
		if profile["resolved"] != false {
			return fmt.Errorf("offline UUID profile unexpectedly resolved")
		}
		if err := client.JSON(ctx, "GET", "/api/players/uuid/invalid/profile", nil, nil, 400); err != nil {
			return err
		}
		return nil
	}); err != nil {
		return err
	}
	if err = client.JSON(ctx, "GET", "/api/config/modules/players", nil, &module, 200); err != nil {
		return err
	}
	module.Data["ignored_name_prefixes"] = []string{"e2e"}
	if err = client.JSON(ctx, "PUT", "/api/config/modules/players", map[string]any{"config_data": module.Data}, nil, 200); err != nil {
		return err
	}
	return t.Step("cleanup previews and deletes only matching players and dependent history", func() error {
		var preview struct {
			Candidates []map[string]any `json:"candidates"`
		}
		if err := client.JSON(ctx, "GET", "/api/players/cleanup/ignored_name_prefix/preview", nil, &preview, 200); err != nil {
			return err
		}
		if len(preview.Candidates) != 1 || preview.Candidates[0]["session_count"] != float64(1) || preview.Candidates[0]["chat_message_count"] != float64(2) || preview.Candidates[0]["achievement_count"] != float64(1) {
			return fmt.Errorf("cleanup preview mismatches real history: %v", preview)
		}
		var removed struct {
			Count int `json:"deleted_count"`
		}
		if err := client.JSON(ctx, "DELETE", "/api/players/cleanup/ignored_name_prefix", nil, &removed, 200); err != nil {
			return err
		}
		if removed.Count != 1 {
			return fmt.Errorf("cleanup removed %d players", removed.Count)
		}
		if err := client.JSON(ctx, "GET", "/api/players/uuid/"+playerUUID, nil, nil, 404); err != nil {
			return err
		}
		if err := client.JSON(ctx, "GET", "/api/players/uuid/"+readyUUID, nil, nil, 200); err != nil {
			return err
		}
		for _, suffix := range []string{"sessions", "chat", "achievements"} {
			var rows []any
			if err := client.JSON(ctx, "GET", fmt.Sprintf("/api/players/%d/%s", p.ID, suffix), nil, &rows, 200); err != nil {
				return err
			}
			if len(rows) != 0 {
				return fmt.Errorf("cleanup retained %s", suffix)
			}
		}
		if err := client.JSON(ctx, "DELETE", "/api/players/cleanup/ignored_name_prefix", nil, &removed, 200); err != nil {
			return err
		}
		if removed.Count != 0 {
			return fmt.Errorf("cleanup is not idempotent")
		}
		return client.JSON(ctx, "GET", "/api/players/cleanup/unknown/preview", nil, nil, 422)
	})
}
