package world

import (
	"context"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func restorationGeneration(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	version, err := backend.Docker.Run(ctx, "exec", backend.Name, "restic", "version")
	if err != nil {
		return err
	}
	if !strings.HasPrefix(strings.TrimSpace(version), "restic 0.18.1 compiled") {
		return fmt.Errorf("restore qualification requires restic 0.18.1, received %q", version)
	}
	t.Recorder.Event("adapter_version", map[string]string{"tool": "restic", "version": strings.TrimSpace(version)})
	if err = s.seedStoppedWorld(); err != nil {
		return err
	}
	selection := map[string]any{"type": "dimension", "region_dir_relpath": fixtureRegion}
	snapshot, err := s.snapshot(ctx, selection)
	if err != nil {
		return err
	}
	if err = s.seedRegion([2]string{"old incarnation safety zero", "old incarnation safety one"}); err != nil {
		return err
	}
	complete, err := s.client.SSE(ctx, "POST", s.base+"/world-restore/restore", request(snapshot, selection), "complete")
	if err != nil {
		return err
	}
	id, _ := complete["restoration_id"].(string)
	var original restoration
	if id == "" {
		return fmt.Errorf("restore has no durable history ID")
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/world-restore/restorations/"+id, nil, &original, 200); err != nil {
		return err
	}
	if original.Generation == nil || *original.Generation <= 0 || original.BindingIssue != nil || original.Status != "succeeded" || !original.SafetyExists {
		return fmt.Errorf("new restoration lacks an unambiguous generation: %+v", original)
	}
	if err = fixtures.Operation(ctx, s.client, s.id, "remove"); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "POST", s.base, map[string]string{"yaml_content": fixtures.ServerOf(t.Env).Compose}, nil, 200); err != nil {
		return err
	}
	if err = s.seedStoppedWorld(); err != nil {
		return err
	}
	current := [2]string{"replacement generation zero", "replacement generation one"}
	if err = s.seedRegion(current); err != nil {
		return err
	}
	checkHistoryAndData := func() error {
		var history struct {
			Total int           `json:"total"`
			Rows  []restoration `json:"restorations"`
		}
		if err := s.client.JSON(ctx, "GET", s.base+"/world-restore/restorations", nil, &history, 200); err != nil {
			return err
		}
		if history.Total != 1 || len(history.Rows) != 1 || history.Rows[0].ID != id {
			return fmt.Errorf("same-name recreation hid old restoration history: %+v", history)
		}
		var old restoration
		if err := s.client.JSON(ctx, "GET", s.base+"/world-restore/restorations/"+id, nil, &old, 200); err != nil {
			return err
		}
		if old.Generation == nil || *old.Generation != *original.Generation || old.Safety != original.Safety || !old.SafetyExists || old.Status != original.Status || old.BindingIssue == nil || *old.BindingIssue != "generation_changed" {
			return fmt.Errorf("old history was rebound or modified during recreation: %+v", old)
		}
		if err := s.conflict(ctx, s.base+"/world-restore/restorations/"+id+"/rollback", nil, "restoration_identity_conflict"); err != nil {
			return err
		}
		for x := range 2 {
			expected, _ := chunkPayload(regionData(current), x)
			if err := s.checkChunk(ctx, x, expected); err != nil {
				return fmt.Errorf("old restoration altered a same-name replacement: %w", err)
			}
		}
		return nil
	}
	if err = t.Step("old restoration history remains visible but cannot roll back a new instance", checkHistoryAndData); err != nil {
		return err
	}
	if err = fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
		return err
	}
	if err = t.Step("generation protection survives backend restart", checkHistoryAndData); err != nil {
		return err
	}
	newSnapshot, err := s.snapshot(ctx, selection)
	if err != nil {
		return err
	}
	complete, err = s.client.SSE(ctx, "POST", s.base+"/world-restore/restore", request(newSnapshot, selection), "complete")
	if err != nil {
		return err
	}
	newID, _ := complete["restoration_id"].(string)
	var replacement restoration
	if err = s.client.JSON(ctx, "GET", s.base+"/world-restore/restorations/"+newID, nil, &replacement, 200); err != nil {
		return err
	}
	if replacement.Generation == nil || *replacement.Generation <= *original.Generation || replacement.BindingIssue != nil || replacement.Status != "succeeded" {
		return fmt.Errorf("current instance cannot restore using its own generation: %+v", replacement)
	}
	return nil
}
