package players

import (
	"context"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func legacy(ctx context.Context, t *engine.Scope) error {
	b := fixtures.BackendOf(t.Env)
	if _, err := b.Docker.Run(ctx, "stop", "--time", "10", b.Name); err != nil {
		return err
	}
	const seed = `import sqlite3,sys,base64,datetime
db=sqlite3.connect('/data/db.sqlite3')
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
server=db.execute('select id from server where server_id=?',(sys.argv[1],)).fetchone()[0]
avatar=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL3sAAAAASUVORK5CYII=')
for uuid,name in [('123e4567e89b32d3a456426614174002','OfflineLegacy'),('123e4567e89b42d3a456426614174000','CachedFixture')]:
    row=db.execute('insert into player(uuid,current_name,skin_data,avatar_data,last_skin_update,created_at) values(?,?,?,?,?,?)',(uuid,name,avatar,avatar,now,now)).lastrowid
    if name=='OfflineLegacy':
        db.execute('insert into player_session(player_db_id,server_db_id,joined_at,left_at,duration_seconds) values(?,?,?,?,?)',(row,server,now,now,0))
        db.execute('insert into player_chat_message(player_db_id,server_db_id,message_text,sent_at) values(?,?,?,?)',(row,server,'legacy chat',now))
        db.execute('insert into player_achievement(player_db_id,server_db_id,achievement_name,earned_at) values(?,?,?,?)',(row,server,'legacy advancement',now))
db.commit()
`
	if _, err := fixtures.DeploymentCommand(ctx, t.Env, "legacy-player-input", "python", "-c", seed, fixtures.ServerOf(t.Env).ID); err != nil {
		return err
	}
	if err := b.Restart(ctx); err != nil {
		return err
	}
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	if err = t.Step("cached profiles stream normalized unique results without external fetching", func() error {
		var profile map[string]any
		if err := client.JSON(ctx, "GET", "/api/players/uuid/123e4567-e89b-42d3-a456-426614174000/profile", nil, &profile, 200); err != nil {
			return err
		}
		if profile["resolved"] != true || profile["current_name"] != "CachedFixture" || profile["avatar_base64"] == nil {
			return fmt.Errorf("cached profile not preserved")
		}
		seen := map[string]int{}
		terminal, err := client.SSEEvents(ctx, "POST", "/api/players/profiles/stream", map[string]any{"uuids": []string{playerUUID, strings.ToUpper(playerUUID), offlineUUID, "invalid", "invalid"}}, "complete", func(event map[string]any) error {
			if event["event_type"] == "profile" {
				p, ok := event["profile"].(map[string]any)
				if !ok {
					return fmt.Errorf("profile event missing payload")
				}
				seen[fmt.Sprint(p["uuid"])]++
			}
			return nil
		})
		if err != nil {
			return err
		}
		if terminal["total"] != float64(3) || terminal["resolved"] != float64(1) || len(seen) != 3 {
			return fmt.Errorf("profile stream normalization/resolution mismatch: %v %v", terminal, seen)
		}
		for _, count := range seen {
			if count != 1 {
				return fmt.Errorf("duplicate profile emitted")
			}
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("offline legacy cleanup previews exact dependent counts and preserves online identity", func() error {
		var preview struct {
			Candidates []struct {
				ID           int `json:"player_db_id"`
				Sessions     int `json:"session_count"`
				Chat         int `json:"chat_message_count"`
				Achievements int `json:"achievement_count"`
			} `json:"candidates"`
		}
		if err := client.JSON(ctx, "GET", "/api/players/cleanup/offline_uuid/preview", nil, &preview, 200); err != nil {
			return err
		}
		if len(preview.Candidates) != 1 || preview.Candidates[0].Sessions != 1 || preview.Candidates[0].Chat != 1 || preview.Candidates[0].Achievements != 1 {
			return fmt.Errorf("incorrect legacy cleanup preview: %+v", preview)
		}
		id := preview.Candidates[0].ID
		if err := client.JSON(ctx, "POST", fmt.Sprintf("/api/players/%d/refresh-skin", id), nil, nil, 200); err != nil {
			return err
		}
		var removed struct {
			Count int `json:"deleted_count"`
		}
		if err := client.JSON(ctx, "DELETE", "/api/players/cleanup/offline_uuid", nil, &removed, 200); err != nil {
			return err
		}
		if removed.Count != 1 {
			return fmt.Errorf("legacy cleanup count=%d", removed.Count)
		}
		for _, suffix := range []string{"sessions", "chat", "achievements"} {
			var rows []any
			if err := client.JSON(ctx, "GET", fmt.Sprintf("/api/players/%d/%s", id, suffix), nil, &rows, 200); err != nil {
				return err
			}
			if len(rows) != 0 {
				return fmt.Errorf("legacy cleanup retained %s", suffix)
			}
		}
		if err := client.JSON(ctx, "POST", fmt.Sprintf("/api/players/%d/refresh-skin", id), nil, nil, 404); err != nil {
			return err
		}
		if err := client.JSON(ctx, "GET", "/api/players/uuid/"+playerUUID, nil, nil, 200); err != nil {
			return err
		}
		if err := client.JSON(ctx, "DELETE", "/api/players/cleanup/offline_uuid", nil, &removed, 200); err != nil {
			return err
		}
		if removed.Count != 0 {
			return fmt.Errorf("legacy cleanup not idempotent")
		}
		return nil
	})
}

func liveProfile(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	const uuid = "069a79f444e94726a5befca90e38aaf5"
	var profile struct {
		ID       int    `json:"player_db_id"`
		Resolved bool   `json:"resolved"`
		Avatar   string `json:"avatar_base64"`
		Name     string `json:"current_name"`
		Updated  string `json:"last_skin_update"`
	}
	path := "/api/players/uuid/" + uuid + "/profile"
	return t.Step("actual Mojang profile and skin fetch populates the persistent cache", func() error {
		if err := client.JSON(ctx, "GET", path, nil, &profile, 200); err != nil {
			return err
		}
		if !profile.Resolved || profile.ID == 0 || profile.Avatar == "" || profile.Name == "" || profile.Updated == "" {
			return fmt.Errorf("live Mojang profile/skin unavailable; selected external test requires Mojang reachability")
		}
		if err := client.JSON(ctx, "POST", fmt.Sprintf("/api/players/%d/refresh-skin", profile.ID), nil, nil, 200); err != nil {
			return err
		}
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		var persisted map[string]any
		if err := client.JSON(ctx, "GET", path, nil, &persisted, 200); err != nil {
			return err
		}
		if persisted["avatar_base64"] == nil || persisted["resolved"] != true {
			return fmt.Errorf("downloaded profile cache did not survive restart")
		}
		return nil
	})
}
