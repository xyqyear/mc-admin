package players

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func crashRecovery(ctx context.Context, t *engine.Scope) error {
	b := fixtures.BackendOf(t.Env)
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	if err = fixtures.CreateFile(ctx, client, fixtures.ServerOf(t.Env).ID, "/usercache.json", `[{"name":"RecoveredFixture","uuid":"123e4567-e89b-42d3-a456-426614174000"},{"name":"LateFixture","uuid":"123e4567-e89b-42d3-a456-426614174001"}]`); err != nil {
		return err
	}
	if _, err = b.Docker.Run(ctx, "stop", "--time", "10", b.Name); err != nil {
		return err
	}
	const seed = `import sqlite3,sys,datetime
db=sqlite3.connect('/data/db.sqlite3')
crash=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=1)
joined=crash-datetime.timedelta(seconds=120)
server=db.execute('select id from server where server_id=?',(sys.argv[1],)).fetchone()[0]
player=db.execute('insert into player(uuid,current_name,created_at) values(?,?,?)',('123e4567e89b42d3a456426614174000','RecoveredFixture',joined.isoformat())).lastrowid
db.execute('insert into player_session(player_db_id,server_db_id,joined_at) values(?,?,?)',(player,server,joined.isoformat()))
late_joined=crash+datetime.timedelta(seconds=10)
late=db.execute('insert into player(uuid,current_name,created_at) values(?,?,?)',('123e4567e89b42d3a456426614174001','LateFixture',late_joined.isoformat())).lastrowid
db.execute('insert into player_session(player_db_id,server_db_id,joined_at) values(?,?,?)',(late,server,late_joined.isoformat()))
db.execute('insert or replace into system_heartbeat(id,timestamp) values(1,?)',(crash.isoformat(),))
db.commit()
`
	if _, err = fixtures.DeploymentCommand(ctx, t.Env, "crash-history-input", "python", "-c", seed, fixtures.ServerOf(t.Env).ID); err != nil {
		return err
	}
	return t.Step("startup closes stale open sessions at the last heartbeat and preserves playtime", func() error {
		if err := b.Restart(ctx); err != nil {
			return err
		}
		p, err := waitDetail(ctx, client, playerUUID, func(d detail) bool { return !d.Online && d.Sessions == 1 })
		if err != nil {
			return err
		}
		var sessions []struct {
			Active   bool   `json:"is_active"`
			Duration int    `json:"duration_seconds"`
			Left     string `json:"left_at"`
		}
		if err := client.JSON(ctx, "GET", fmt.Sprintf("/api/players/%d/sessions", p.ID), nil, &sessions, 200); err != nil {
			return err
		}
		if len(sessions) != 1 || sessions[0].Active || sessions[0].Duration != 120 || sessions[0].Left == "" {
			return fmt.Errorf("crash recovery did not close the session at its last heartbeat: %+v", sessions)
		}
		late, err := waitDetail(ctx, client, readyUUID, func(d detail) bool { return !d.Online && d.Sessions == 1 })
		if err != nil {
			return err
		}
		var lateSessions []struct {
			Active   bool      `json:"is_active"`
			Duration int       `json:"duration_seconds"`
			Joined   time.Time `json:"joined_at"`
			Left     time.Time `json:"left_at"`
		}
		if err := client.JSON(ctx, "GET", fmt.Sprintf("/api/players/%d/sessions", late.ID), nil, &lateSessions, 200); err != nil {
			return err
		}
		if len(lateSessions) != 1 || lateSessions[0].Active || lateSessions[0].Duration != 0 || !lateSessions[0].Left.Equal(lateSessions[0].Joined) {
			return fmt.Errorf("post-heartbeat join produced invalid recovery duration: %+v", lateSessions)
		}
		if err := b.Restart(ctx); err != nil {
			return err
		}
		var stats map[string]any
		if err := client.JSON(ctx, "GET", fmt.Sprintf("/api/players/%d/sessions/stats", p.ID), nil, &stats, 200); err != nil {
			return err
		}
		if stats["total_sessions"] != float64(1) || stats["total_playtime_seconds"] != float64(120) {
			return fmt.Errorf("normal restart changed recovered playtime: %v", stats)
		}
		if err := client.JSON(ctx, "GET", fmt.Sprintf("/api/players/%d/sessions/stats", late.ID), nil, &stats, 200); err != nil {
			return err
		}
		if stats["total_sessions"] != float64(1) || stats["total_playtime_seconds"] != float64(0) {
			return fmt.Errorf("late-join recovered playtime changed after restart: %v", stats)
		}
		return nil
	})
}
