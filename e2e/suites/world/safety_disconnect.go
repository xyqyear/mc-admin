package world

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type restoreOperation struct {
	ID             string     `json:"operation_id"`
	Kind           string     `json:"kind"`
	LegacyID       string     `json:"legacy_id"`
	State          string     `json:"state"`
	Origin         string     `json:"origin"`
	ActorID        *int64     `json:"actor_id"`
	Ended          *time.Time `json:"ended_at"`
	WritersStopped bool       `json:"writers_stopped"`
	RecoveryReason *string    `json:"recovery_reason"`
	Resources      []struct {
		Kind       string `json:"kind"`
		ServerID   string `json:"server_id"`
		Generation int64  `json:"generation"`
		Path       string `json:"path"`
	} `json:"resources"`
	RecoveryRefs []struct {
		Kind  string `json:"kind"`
		Value string `json:"value"`
	} `json:"recovery_refs"`
}

func safetySnapshotDisconnect(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.seedStoppedWorld(); err != nil {
		return err
	}
	selection := map[string]any{"type": "dimension", "region_dir_relpath": fixtureRegion}
	snapshot, err := s.snapshot(ctx, selection)
	if err != nil {
		return err
	}
	live := regionData([2]string{"safety snapshot zero", "safety snapshot one"})
	region := fixtureRegion + "/r.0.0.mca"
	if err = s.seed(region, live); err != nil {
		return err
	}
	disconnect := errors.New("close SSE on the first persisted safety snapshot")
	var id, safety string
	_, err = s.client.SSEEvents(ctx, "POST", s.base+"/world-restore/restore", request(snapshot, selection), "complete", func(event map[string]any) error {
		if event["event_type"] != "safety_snapshot" {
			return nil
		}
		safety, _ = event["safety_snapshot_id"].(string)
		if safety == "" {
			return nil
		}
		id, _ = event["restoration_id"].(string)
		return disconnect
	})
	if !errors.Is(err, disconnect) || id == "" || safety == "" {
		return fmt.Errorf("restore did not expose a persisted safety snapshot before disconnect: id=%q safety=%q error=%v", id, safety, err)
	}
	t.Recorder.Event("restore_safety_disconnect", map[string]string{"restoration_id": id, "safety_snapshot_id": safety})
	if err = t.Step("early disconnect settles matching history and operation without restarting the application", func() error {
		return s.waitSafetyDisconnect(ctx, id, safety)
	}); err != nil {
		return err
	}
	if err = t.Step("independent persisted management writes still work after disconnection", func() error {
		return s.managementWritesAfterDisconnect(ctx)
	}); err != nil {
		return err
	}
	if err = s.seedRegion([2]string{"changed after disconnect zero", "changed after disconnect one"}); err != nil {
		return err
	}
	if _, err = s.client.SSE(ctx, "POST", s.base+"/world-restore/restorations/"+id+"/rollback", nil, "complete"); err != nil {
		return err
	}
	restored, err := s.download(ctx, region)
	if err != nil {
		return err
	}
	if !bytes.Equal(restored, live) {
		return fmt.Errorf("early-disconnect safety rollback did not restore the exact pre-request region bytes")
	}
	return fixtures.Status(ctx, s.client, s.id, "exists")
}

func (s *scenario) waitSafetyDisconnect(ctx context.Context, id, safety string) error {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	return api.Wait(ctx, 100*time.Millisecond, "early SSE disconnection releases history, journal and maintenance", func(ctx context.Context) (bool, error) {
		var history restoration
		if err := s.client.JSON(ctx, "GET", s.base+"/world-restore/restorations/"+id, nil, &history, 200); err != nil {
			return false, api.Permanent(err)
		}
		if history.ID != id || history.Safety != safety || !history.SafetyExists || history.Generation == nil || *history.Generation <= 0 {
			return false, api.Permanent(fmt.Errorf("early-disconnect history lost its persisted safety reference or generation: %+v", history))
		}
		if history.Status == "running" {
			return false, fmt.Errorf("restoration %s is still running", id)
		}
		if (history.Status != "interrupted" && history.Status != "succeeded") || history.Finished == nil || *history.Finished == "" {
			return false, api.Permanent(fmt.Errorf("early-disconnect history did not settle safely: %+v", history))
		}
		var operations []restoreOperation
		if err := s.client.JSON(ctx, "GET", "/api/operations?limit=1000", nil, &operations, 200); err != nil {
			return false, api.Permanent(err)
		}
		var matches []restoreOperation
		for _, operation := range operations {
			if operation.Kind == "world_restore" && operation.LegacyID == id {
				matches = append(matches, operation)
			}
		}
		if len(matches) != 1 {
			return false, api.Permanent(fmt.Errorf("restoration %s has %d matching durable operations", id, len(matches)))
		}
		operation := matches[0]
		switch operation.State {
		case "queued", "running", "cancelling", "finalizing":
			return false, fmt.Errorf("restoration operation %s is still %s", operation.ID, operation.State)
		}
		settled := operation.State == history.Status || (history.Status == "succeeded" && operation.State == "interrupted")
		if operation.ID == "" || !settled || operation.Ended == nil || !operation.WritersStopped || operation.RecoveryReason != nil || operation.Origin != "request" || operation.ActorID == nil || *operation.ActorID <= 0 {
			return false, api.Permanent(fmt.Errorf("early-disconnect operation disagrees with safe terminal history: %+v", operation))
		}
		bound := false
		for _, resource := range operation.Resources {
			if resource.ServerID != s.id || resource.Generation != *history.Generation {
				return false, api.Permanent(fmt.Errorf("operation %s resource is bound to another server generation: %+v", operation.ID, resource))
			}
			if resource.Kind == "files" && resource.Path == "data/"+fixtureRegion {
				bound = true
			}
		}
		safetyRetained, historyRetained := false, false
		for _, reference := range operation.RecoveryRefs {
			if reference.Kind == "safety_snapshot" && reference.Value == safety {
				safetyRetained = true
			}
			if reference.Kind == "restoration" && reference.Value == id {
				historyRetained = true
			}
		}
		if !bound || !safetyRetained || !historyRetained {
			return false, api.Permanent(fmt.Errorf("operation %s lost its exact region file scope or recovery references", operation.ID))
		}
		var maintenance struct {
			Active bool `json:"active"`
		}
		if err := s.client.JSON(ctx, "GET", s.base+"/maintenance", nil, &maintenance, 200); err != nil {
			return false, api.Permanent(err)
		}
		if maintenance.Active {
			return false, fmt.Errorf("terminal restoration %s still owns maintenance", id)
		}
		s.t.Recorder.Event("restore_safety_disconnect_terminal", map[string]string{"restoration_id": id, "operation_id": operation.ID, "history_status": history.Status, "operation_state": operation.State})
		return true, nil
	})
}

func (s *scenario) managementWritesAfterDisconnect(ctx context.Context) error {
	if err := s.config(ctx, "mcmap", func(config map[string]any) { config["prune_preview_ttl_seconds"] = 1801 }); err != nil {
		return err
	}
	var configuration struct {
		Data struct {
			TTL int `json:"prune_preview_ttl_seconds"`
		} `json:"config_data"`
	}
	if err := s.client.JSON(ctx, "GET", "/api/config/modules/mcmap", nil, &configuration, 200); err != nil {
		return err
	}
	if configuration.Data.TTL != 1801 {
		return fmt.Errorf("configuration write after disconnect was not persisted")
	}
	id := "safety-disconnect-" + s.id
	path := "/api/cron/" + id
	body := map[string]any{"cronjob_id": id, "identifier": "restart_server", "params": map[string]any{"server_id": s.id}, "cron": "0 0 1 1 *", "second": "0", "name": "E2E write after restore disconnect"}
	if err := s.client.JSON(ctx, "POST", "/api/cron/", body, nil, 200); err != nil {
		return err
	}
	s.t.Cleanup(func(ctx context.Context) error { return s.client.JSON(ctx, "DELETE", path, nil, nil, 200) })
	if err := s.client.JSON(ctx, "POST", path+"/pause", nil, nil, 200); err != nil {
		return err
	}
	var cron struct {
		ID           string `json:"cronjob_id"`
		Status       string `json:"status"`
		Registration string `json:"registration_status"`
	}
	if err := s.client.JSON(ctx, "GET", path, nil, &cron, 200); err != nil {
		return err
	}
	if cron.ID != id || cron.Status != "paused" || cron.Registration != "inactive" {
		return fmt.Errorf("cron management writes after disconnect were not persisted: %+v", cron)
	}
	return nil
}
