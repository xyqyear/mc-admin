package players

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/engine"
)

func logParserDefaults(ctx context.Context, t *engine.Scope) error {
	s, err := prepare(ctx, t)
	if err != nil {
		return err
	}
	connection, err := s.client.OpenWebSocket(ctx, "/api/events?since=0")
	if err != nil {
		return err
	}
	defer connection.CloseNow()
	type observedPlayer struct{ name, uuid string }
	players := []observedPlayer{{"E2EPlayer", playerUUID}, {"ReadyFixture", readyUUID}}
	expectedMessages := []string{}
	expectedAchievements := 0
	playerIDs := map[string]int{}
	observePlayer := func(kind string, player observedPlayer, message string) error {
		forbidden := []string{"player_leave", "server_stopping"}
		if kind == "chat" {
			forbidden = append(forbidden, "player_join")
		} else {
			forbidden = append(forbidden, "chat")
		}
		event, err := readEvent(ctx, t, connection, kind, forbidden...)
		if err != nil {
			return err
		}
		identity, ok := event["player"].(map[string]any)
		if !ok || event["server_id"] != s.id || identity["name"] != player.name || identity["uuid"] != player.uuid {
			return fmt.Errorf("unexpected %s identity: %v", kind, event)
		}
		if kind == "chat" && event["message"] != message {
			return fmt.Errorf("unexpected chat before processing barrier: %v", event)
		}
		return nil
	}
	checkSessions := func(online bool, sessionCount int) error {
		for index, player := range players {
			var got detail
			if err := s.client.JSON(ctx, "GET", "/api/players/uuid/"+player.uuid, nil, &got, 200); err != nil {
				return err
			}
			messages, achievements := 0, 0
			if index == 0 {
				messages, achievements = len(expectedMessages), expectedAchievements
			}
			if got.Name != player.name || got.UUID != player.uuid || got.Online != online || got.Sessions != sessionCount || got.Messages != messages || got.Achievements != achievements {
				return fmt.Errorf("parser observations changed player history: %+v", got)
			}
			playerIDs[player.name] = got.ID
			var sessions []struct {
				Joined   time.Time  `json:"joined_at"`
				Left     *time.Time `json:"left_at"`
				Duration *int       `json:"duration_seconds"`
				Active   bool       `json:"is_active"`
			}
			if err := s.client.JSON(ctx, "GET", fmt.Sprintf("/api/players/%d/sessions?server_id=%s", got.ID, s.id), nil, &sessions, 200); err != nil {
				return err
			}
			if len(sessions) != sessionCount {
				return fmt.Errorf("expected %d sessions for %s, got %d", sessionCount, player.name, len(sessions))
			}
			active := 0
			for _, session := range sessions {
				if session.Active {
					active++
					if session.Left != nil || session.Duration != nil {
						return fmt.Errorf("active session already has an end: %+v", session)
					}
				} else if session.Left == nil || session.Duration == nil || session.Left.Before(session.Joined) || *session.Duration != int(session.Left.Sub(session.Joined).Seconds()) {
					return fmt.Errorf("closed session has invalid time or duration: %+v", session)
				}
			}
			if (online && active != 1) || (!online && active != 0) {
				return fmt.Errorf("unexpected active session count for %s: %d", player.name, active)
			}
		}
		return nil
	}
	rounds := []struct {
		name, address, primarySuffix, secondarySuffix, stop string
	}{
		{"hidden address and ordinary stop", "IP hidden", " at (0.0, 64.0, 0.0)", "", "Stopping server"},
		{"local address and Paper stop", "local", "", "", "Stopping server (Ignore any thread death message you see! - DO NOT REPORT THREAD DEATH TO PAPER)"},
		{"Sponge IPv6 login and missing startup script stop", "/[2001:db8::1]:25565", " in DIM-1(-1) at (1.0, 65.0, -1.0)", " in world(0) at (2.0, 64.0, 2.0)", "Startup script './start.sh' does not exist! Stopping server."},
	}
	for index, round := range rounds {
		if err = t.Step(round.name, func() error {
			if err := s.append(ctx,
				fmt.Sprintf("[12:00:01] [Server thread/INFO]: E2EPlayer[%s] logged in with entity id -1%s", round.address, round.primarySuffix),
				fmt.Sprintf("[12:00:02] [Server thread/INFO]: ReadyFixture[%s] logged in with entity id 2%s", round.address, round.secondarySuffix),
				"[12:00:03] [Server thread/INFO]: E2EPlayer joined the game",
				"[12:00:04] [Server thread/INFO]: ReadyFixture joined the game",
			); err != nil {
				return err
			}
			for _, player := range players {
				if err := observePlayer("player_join", player, ""); err != nil {
					return err
				}
			}
			lines := []string{}
			messages := []string{fmt.Sprintf("parser barrier %d", index+1)}
			if index == 0 {
				lines = append(lines,
					"[12:00:05] [Server thread/INFO]: E2EPlayer has made the advancement [Stone Age]",
					"[12:00:06] [Server thread/INFO]: \x1b[32mE2EPlayer the Brave\x1b[0m has reached the goal \x1b[35m[Explore [Beyond] <Far>]\x1b[0m",
					"[12:00:07] [Server thread/INFO]: E2EPlayer has completed the challenge [Trial [Expert]]",
					"[12:00:08] [Server thread/INFO]: E2EPlayer has just earned the achievement [Getting Wood]",
					"[12:00:09] [Server thread/INFO]: E2EPlayer has completed the challenge [Trial [Expert]]",
					"[12:00:10] [main/DEBUG]: Patching method: <E2EPlayer> diagnostic method",
					"[12:00:11] [Server thread/ERROR]: Invalid type override entry: <ReadyFixture> diagnostic resource",
					"[12:00:12] [Server thread/INFO]: Quoted login: E2EPlayer[/192.0.2.4:25565] logged in with entity id 9",
					"[12:00:13] [Server thread/INFO]: Diagnostic mentions Stopping server",
					"[12:00:14] [Server thread/INFO] [M3[INFO]/]: [Not Secure] <E2EPlayer> E2EPlayer has completed the challenge [Quoted Award]",
				)
				messages = append([]string{"E2EPlayer has completed the challenge [Quoted Award]"}, messages...)
				expectedAchievements = 4
			}
			if index == 1 {
				messages[0] = "Stopping server"
			}
			lines = append(lines, "[12:00:15] [Server thread/INFO]: <E2EPlayer> "+messages[len(messages)-1])
			if err := s.append(ctx, lines...); err != nil {
				return err
			}
			for _, message := range messages {
				if err := observePlayer("chat", players[0], message); err != nil {
					return err
				}
				expectedMessages = append(expectedMessages, message)
			}
			if err := checkSessions(true, index+1); err != nil {
				return err
			}
			if err := s.append(ctx, "[12:00:16] [Server thread/INFO]: "+round.stop); err != nil {
				return err
			}
			stopping, err := readEvent(ctx, t, connection, "server_stopping", "player_join", "player_leave", "chat")
			if err != nil {
				return err
			}
			if stopping["server_id"] != s.id {
				return fmt.Errorf("stopping event has wrong server: %v", stopping)
			}
			return checkSessions(false, index+1)
		}); err != nil {
			return err
		}
	}
	return t.Step("public history preserves clean titles and only actual player chat", func() error {
		var achievements []struct {
			Name   string `json:"achievement_name"`
			Server string `json:"server_id"`
		}
		base := fmt.Sprintf("/api/players/%d", playerIDs["E2EPlayer"])
		if err := s.client.JSON(ctx, "GET", base+"/achievements", nil, &achievements, 200); err != nil {
			return err
		}
		wantTitles := map[string]bool{"Stone Age": true, "Explore [Beyond] <Far>": true, "Trial [Expert]": true, "Getting Wood": true}
		if len(achievements) != len(wantTitles) {
			return fmt.Errorf("unexpected achievement count: %v", achievements)
		}
		for _, achievement := range achievements {
			if !wantTitles[achievement.Name] || achievement.Server != s.id {
				return fmt.Errorf("polluted or misattributed achievement: %+v", achievement)
			}
			delete(wantTitles, achievement.Name)
		}
		var chats []struct {
			Message string `json:"message_text"`
			Server  string `json:"server_id"`
		}
		if err := s.client.JSON(ctx, "GET", base+"/chat", nil, &chats, 200); err != nil {
			return err
		}
		if len(chats) != len(expectedMessages) {
			return fmt.Errorf("diagnostic fragments reached chat history: %v", chats)
		}
		wantMessages := map[string]bool{}
		for _, message := range expectedMessages {
			wantMessages[message] = true
		}
		for _, chat := range chats {
			if !wantMessages[chat.Message] || chat.Server != s.id {
				return fmt.Errorf("unexpected persisted chat: %+v", chat)
			}
			delete(wantMessages, chat.Message)
		}
		return nil
	})
}
