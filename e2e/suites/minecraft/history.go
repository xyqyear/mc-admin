package minecraft

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/fixtures"
)

type lifecycleOperation struct {
	ID             string     `json:"operation_id"`
	Kind           string     `json:"kind"`
	ActorID        *int       `json:"actor_id"`
	Origin         string     `json:"origin"`
	LegacyID       *string    `json:"legacy_id"`
	RunningIntent  *bool      `json:"running_intent"`
	State          string     `json:"state"`
	Phase          string     `json:"phase"`
	Created        time.Time  `json:"created_at"`
	Ended          *time.Time `json:"ended_at"`
	WritersStopped bool       `json:"writers_stopped"`
	RecoveryReason *string    `json:"recovery_reason"`
	Resources      []struct {
		Kind       string `json:"kind"`
		ServerID   string `json:"server_id"`
		Generation int    `json:"generation"`
	} `json:"resources"`
}

type lifecycleHistory struct {
	client     *api.Client
	serverID   string
	actorID    int
	generation int
}

func (h *lifecycleHistory) run(ctx context.Context, action string) error {
	var before, after []lifecycleOperation
	if err := h.client.JSON(ctx, "GET", "/api/operations?limit=1000", nil, &before, 200); err != nil {
		return err
	}
	seen := make(map[string]bool, len(before))
	for _, operation := range before {
		seen[operation.ID] = true
	}
	if err := fixtures.Operation(ctx, h.client, h.serverID, action); err != nil {
		return err
	}
	if err := h.client.JSON(ctx, "GET", "/api/operations?limit=1000", nil, &after, 200); err != nil {
		return err
	}
	expectedPhase := map[string]string{
		"up": "server_started", "start": "server_started", "restart": "server_restarted",
		"stop": "server_stopped", "down": "server_down",
	}[action]
	wantRunning := action == "up" || action == "start" || action == "restart"
	matched := 0
	for _, operation := range after {
		if seen[operation.ID] || operation.Kind != "server_"+action {
			continue
		}
		matched++
		if operation.ID == "" || operation.State != "succeeded" || operation.Phase != expectedPhase || operation.Ended == nil || operation.Ended.Before(operation.Created) || !operation.WritersStopped || operation.RecoveryReason != nil {
			return fmt.Errorf("manual %s lost its confirmed successful history: %+v", action, operation)
		}
		if operation.ActorID == nil || *operation.ActorID != h.actorID || operation.Origin != "request" || operation.LegacyID != nil || operation.RunningIntent == nil || *operation.RunningIntent != wantRunning {
			return fmt.Errorf("manual %s lost its caller or running intent: %+v", action, operation)
		}
		if len(operation.Resources) != 1 || operation.Resources[0].Kind != "server" || operation.Resources[0].ServerID != h.serverID || operation.Resources[0].Generation <= 0 {
			return fmt.Errorf("manual %s lost its exact server resource: %+v", action, operation.Resources)
		}
		generation := operation.Resources[0].Generation
		if h.generation != 0 && generation != h.generation {
			return fmt.Errorf("manual %s changed server generation from %d to %d", action, h.generation, generation)
		}
		h.generation = generation
	}
	if matched != 1 {
		return fmt.Errorf("manual %s produced %d new history records, expected one", action, matched)
	}
	return nil
}
