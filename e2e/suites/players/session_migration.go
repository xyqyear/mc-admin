package players

import (
	"context"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func duplicateSessionMigration(ctx context.Context, t *engine.Scope) error {
	b := fixtures.BackendOf(t.Env)
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	if err = fixtures.CreateFile(ctx, c, id, "/usercache.json", `[{"name":"RepairFixture","uuid":"123e4567-e89b-42d3-a456-426614174000"}]`); err != nil {
		return err
	}
	if _, err = b.Docker.Run(ctx, "stop", "--time", "10", b.Name); err != nil {
		return err
	}
	if _, err = fixtures.DeploymentCommand(ctx, t.Env, "session-downgrade", "alembic", "-c", "/app/alembic.ini", "downgrade", "2026090700"); err != nil {
		return err
	}
	const seed = `import sqlite3,sys,datetime
db=sqlite3.connect('/data/db.sqlite3')
crash=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=1)
server=db.execute('select id from server where server_id=?',(sys.argv[1],)).fetchone()[0]
player=db.execute('insert into player(uuid,current_name,created_at) values(?,?,?)',('123e4567e89b42d3a456426614174000','RepairFixture',crash.isoformat())).lastrowid
for sid,joined,left,duration in [(101,crash-datetime.timedelta(seconds=120),None,None),(102,crash-datetime.timedelta(seconds=30),None,None),(103,crash-datetime.timedelta(seconds=360),crash-datetime.timedelta(seconds=300),60)]:
 db.execute('insert into player_session(session_id,player_db_id,server_db_id,joined_at,left_at,duration_seconds) values(?,?,?,?,?,?)',(sid,player,server,joined.isoformat(),left.isoformat() if left else None,duration))
db.execute('insert or replace into system_heartbeat(id,timestamp) values(1,?)',(crash.isoformat(),))
db.commit()
`
	if _, err = fixtures.DeploymentCommand(ctx, t.Env, "session-history-input", "python", "-c", seed, id); err != nil {
		return err
	}
	if err = t.Step("duplicate history fails migration before an explicit reviewed repair", func() error {
		output, err := fixtures.DeploymentCommand(ctx, t.Env, "session-upgrade-refused", "alembic", "-c", "/app/alembic.ini", "upgrade", "head")
		if err == nil || !strings.Contains(output, "重复未结束玩家会话") {
			return fmt.Errorf("duplicate session migration did not fail with repair guidance: %v %s", err, output)
		}
		if _, err := fixtures.DeploymentCommand(ctx, t.Env, "session-repair-preview", "python", "-m", "app.db.session_repair", "preview", "--database", "/data/db.sqlite3", "--report", "/data/session-repair-plan.json"); err != nil {
			return err
		}
		output, err = fixtures.DeploymentCommand(ctx, t.Env, "session-repair-report", "python", "-c", "import json; p=json.load(open('/data/session-repair-plan.json')); assert len(p['groups'])==1; g=p['groups'][0]; assert g['canonical']['session_id']==101; assert len(g['changes'])==1 and g['changes'][0]['before']['session_id']==102; print(json.dumps(p))")
		if err != nil {
			return err
		}
		t.Recorder.Event("session_repair_review", map[string]any{"report": output})
		_, err = fixtures.DeploymentCommand(ctx, t.Env, "session-repair-apply", "python", "-m", "app.db.session_repair", "apply", "--database", "/data/db.sqlite3", "--report", "/data/session-repair-plan.json", "--evidence", "/data/session-repair-evidence.json")
		return err
	}); err != nil {
		return err
	}
	return t.Step("upgraded API preserves historical IDs and counts repaired playtime once", func() error {
		if err := b.Restart(ctx); err != nil {
			return err
		}
		player, err := waitDetail(ctx, c, playerUUID, func(d detail) bool { return !d.Online && d.Sessions == 3 })
		if err != nil {
			return err
		}
		var sessions []struct {
			ID       int  `json:"session_id"`
			Duration int  `json:"duration_seconds"`
			Active   bool `json:"is_active"`
		}
		if err = c.JSON(ctx, "GET", fmt.Sprintf("/api/players/%d/sessions", player.ID), nil, &sessions, 200); err != nil {
			return err
		}
		expected := map[int]int{101: 120, 102: 0, 103: 60}
		if len(sessions) != len(expected) {
			return fmt.Errorf("session repair lost historical rows: %+v", sessions)
		}
		for _, session := range sessions {
			duration, exists := expected[session.ID]
			if !exists || session.Duration != duration || session.Active {
				return fmt.Errorf("session repair changed IDs or duplicated duration: %+v", sessions)
			}
		}
		var stats struct {
			Duration int `json:"total_playtime_seconds"`
		}
		if err = c.JSON(ctx, "GET", fmt.Sprintf("/api/players/%d/sessions/stats", player.ID), nil, &stats, 200); err != nil {
			return err
		}
		if stats.Duration != 180 {
			return fmt.Errorf("repaired playtime is %d, expected 180", stats.Duration)
		}
		return nil
	})
}
