package world

import (
	"context"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type restoration struct {
	ID                string  `json:"id"`
	OperationID       string  `json:"operation_id"`
	RollbackAvailable bool    `json:"rollback_available"`
	Status            string  `json:"status"`
	Safety            string  `json:"safety_snapshot_id"`
	SourceExists      bool    `json:"source_snapshot_exists"`
	SafetyExists      bool    `json:"safety_snapshot_exists"`
	Rollback          bool    `json:"is_rollback"`
	Finished          *string `json:"finished_at"`
	Error             string  `json:"error_message"`
	Generation        *int64  `json:"server_generation"`
	BindingIssue      *string `json:"binding_issue"`
}

func scopedRestore(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "POST", "/api/snapshots/restorations", s.restoreRequest(strings.Repeat("0", 64), map[string]any{"type": "world"}), nil, 409); err != nil {
		return err
	}
	if err = s.stop(ctx); err != nil {
		return err
	}
	if _, err = s.client.RunTaskResult(ctx, "POST", s.base+"/map/initialize", nil); err != nil {
		return err
	}
	before, after := [2]string{"before zero", "before one"}, [2]string{"after zero", "after one"}
	if err = s.seedRegion(before); err != nil {
		return err
	}
	sidecars := []string{"world/dimensions/e2e/testing/entities/r.0.0.mca", "world/dimensions/e2e/testing/poi/r.0.0.mca"}
	for _, file := range sidecars {
		if err = s.seed(file, regionData(before)); err != nil {
			return err
		}
	}
	if err = s.seed("world_other/level.dat", gzipNBT([]byte{10, 0, 0, 0})); err != nil {
		return err
	}
	if err = s.seed("world_other/region/r.0.0.mca", regionData(before)); err != nil {
		return err
	}
	if err = s.createMarker(ctx, "world_other/e2e-world.txt", "before world"); err != nil {
		return err
	}
	if err = s.createMarker(ctx, "world/e2e-world.txt", "before world"); err != nil {
		return err
	}
	snapshot, err := s.snapshot(ctx, map[string]any{"type": "world"})
	if err != nil {
		return err
	}
	dimensionSnapshot, err := s.snapshot(ctx, map[string]any{"type": "dimension", "region_dir_relpath": fixtureRegion})
	if err != nil {
		return err
	}
	if snapshot == dimensionSnapshot {
		return fmt.Errorf("world and dimension snapshots have identical IDs")
	}
	for _, invalid := range []map[string]any{{"type": "dimension"}, {"type": "chunks", "region_dir_relpath": "../outside", "chunks": [][2]int{{0, 0}}}} {
		if err = s.client.JSON(ctx, "POST", "/api/snapshots/eligible", s.scopeRequest(invalid), nil, 422); err != nil {
			return err
		}
	}
	if err = s.client.JSON(ctx, "POST", "/api/snapshots/eligible", s.scopeRequest(map[string]any{"type": "regions", "region_dir_relpath": fixtureRegion}), nil, 422); err != nil {
		return err
	}
	var last restoration
	for _, kind := range []string{"chunks", "regions", "dimension", "world"} {
		selection := map[string]any{"type": kind}
		if kind != "world" {
			selection["region_dir_relpath"] = fixtureRegion
		}
		if kind == "chunks" {
			selection["chunks"] = [][2]int{{0, 0}}
		}
		if kind == "regions" {
			selection["regions"] = [][2]int{{0, 0}}
		}
		var eligible struct {
			Snapshots []struct {
				ID string `json:"id"`
			} `json:"snapshots"`
		}
		if err = s.client.JSON(ctx, "POST", "/api/snapshots/eligible", s.scopeRequest(selection), &eligible, 200); err != nil {
			return err
		}
		found := false
		for _, item := range eligible.Snapshots {
			if item.ID == snapshot {
				found = true
			}
		}
		if !found {
			return fmt.Errorf("world snapshot not eligible for %s", kind)
		}
		if err = s.seedRegion(after); err != nil {
			return err
		}
		for _, file := range sidecars {
			if err = s.seed(file, regionData(after)); err != nil {
				return err
			}
		}
		if err = fixtures.WriteFile(ctx, s.client, s.id, "/world_other/e2e-world.txt", "after world"); err != nil {
			return err
		}
		if err = fixtures.WriteFile(ctx, s.client, s.id, "/world/e2e-world.txt", "after world"); err != nil {
			return err
		}
		preview, err := s.client.SSE(ctx, "POST", s.base+"/world-restore/preview", request(snapshot, selection), "ready")
		if err != nil {
			return err
		}
		session, ok := preview["session_id"].(string)
		if !ok || session == "" {
			return fmt.Errorf("%s preview has no session", kind)
		}
		if err = s.client.JSON(ctx, "DELETE", s.base+"/world-restore/preview/"+session, nil, nil, 204); err != nil {
			return err
		}
		expected0, _ := chunkPayload(regionData(after), 0)
		if err = s.checkChunk(ctx, 0, expected0); err != nil {
			return fmt.Errorf("preview mutated live data: %w", err)
		}
		var checkCache func() error
		if kind == "world" {
			checkCache, err = s.prepareRestoreCacheCheck(ctx)
			if err != nil {
				return err
			}
		}
		completed, err := s.client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations", s.restoreRequest(snapshot, selection))
		if err != nil {
			return err
		}
		id, _ := completed["restoration_id"].(string)
		if id == "" {
			return fmt.Errorf("%s restore omitted history ID", kind)
		}
		if err = s.client.JSON(ctx, "GET", "/api/snapshots/restorations/"+id, nil, &last, 200); err != nil {
			return err
		}
		if last.Status != "succeeded" || last.Safety == "" || !last.SourceExists || !last.SafetyExists || last.Rollback || last.Finished == nil {
			return fmt.Errorf("restore history incomplete: %+v", last)
		}
		expected0, _ = chunkPayload(regionData(before), 0)
		if err = s.checkChunk(ctx, 0, expected0); err != nil {
			return fmt.Errorf("%s restore: %w", kind, err)
		}
		expected1, _ := chunkPayload(regionData(before), 1)
		if kind == "chunks" {
			expected1, _ = chunkPayload(regionData(after), 1)
		}
		if err = s.checkChunk(ctx, 1, expected1); err != nil {
			return fmt.Errorf("%s selection boundary: %w", kind, err)
		}
		for _, file := range sidecars {
			if err = s.checkChunkAt(ctx, file, 0, expected0); err != nil {
				return fmt.Errorf("%s sidecar selection: %w", kind, err)
			}
			if err = s.checkChunkAt(ctx, file, 1, expected1); err != nil {
				return fmt.Errorf("%s sidecar boundary: %w", kind, err)
			}
		}
		marker := "after world"
		if kind == "world" {
			marker = "before world"
		}
		if err = fixtures.CheckFile(ctx, s.client, s.id, "/world/e2e-world.txt", marker); err != nil {
			return err
		}
		if err = fixtures.CheckFile(ctx, s.client, s.id, "/world_other/e2e-world.txt", marker); err != nil {
			return fmt.Errorf("multiworld selection scope: %w", err)
		}
		if checkCache != nil {
			if err = checkCache(); err != nil {
				return fmt.Errorf("restore cache: %w", err)
			}
		}
		rolled, err := s.client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations/"+id+"/rollback", nil)
		if err != nil {
			return err
		}
		rolledID, _ := rolled["restoration_id"].(string)
		var rollback restoration
		if err = s.client.JSON(ctx, "GET", "/api/snapshots/restorations/"+rolledID, nil, &rollback, 200); err != nil {
			return err
		}
		if !rollback.Rollback || rollback.Status != "succeeded" || !rollback.SafetyExists {
			return fmt.Errorf("rollback history incomplete: %+v", rollback)
		}
		if checkCache != nil {
			if err = checkCache(); err != nil {
				return fmt.Errorf("rollback cache: %w", err)
			}
		}
		for x := range 2 {
			expected, _ := chunkPayload(regionData(after), x)
			if err = s.checkChunk(ctx, x, expected); err != nil {
				return fmt.Errorf("%s rollback: %w", kind, err)
			}
		}
	}
	var history struct {
		Total int           `json:"total"`
		Rows  []restoration `json:"restorations"`
	}
	if err = s.client.JSON(ctx, "GET", "/api/snapshots/restorations?limit=2&offset=1&server_id="+s.id, nil, &history, 200); err != nil {
		return err
	}
	if history.Total != 8 || len(history.Rows) != 2 {
		return fmt.Errorf("history pagination returned %d rows total %d", len(history.Rows), history.Total)
	}
	if err = s.client.JSON(ctx, "DELETE", "/api/snapshots/"+last.Safety, nil, nil, 200); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "GET", "/api/snapshots/restorations/"+last.ID, nil, &last, 200); err != nil {
		return err
	}
	if last.SafetyExists {
		return fmt.Errorf("deleted safety snapshot still advertised as available")
	}
	if last.RollbackAvailable {
		return fmt.Errorf("history allows rollback after its safety was deleted")
	}
	accepted, err := s.client.StartTask(ctx, "POST", "/api/snapshots/restorations/"+last.ID+"/rollback", nil)
	if err != nil {
		return err
	}
	failed, err := s.client.Task(ctx, accepted.ID)
	if err == nil || failed.Status != "failed" {
		return fmt.Errorf("missing safety did not fail without applying: %+v: %v", failed, err)
	}
	for _, suffix := range []string{"/restorations/missing", "/restorations?limit=0"} {
		status := 404
		if strings.Contains(suffix, "limit") {
			status = 422
		}
		if err = s.client.JSON(ctx, "GET", "/api/snapshots"+suffix, nil, nil, status); err != nil {
			return err
		}
	}
	return s.client.JSON(ctx, "POST", "/api/snapshots/restorations/missing/rollback", nil, nil, 404)
}

func interruptedRestore(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.stop(ctx); err != nil {
		return err
	}
	if err = s.seedRegion([2]string{"before", "before"}); err != nil {
		return err
	}
	snapshot, err := s.snapshot(ctx, map[string]any{"type": "dimension", "region_dir_relpath": fixtureRegion})
	if err != nil {
		return err
	}
	if err = s.seedRegion([2]string{"recover zero", "recover one"}); err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	if err = startResticPauses(ctx, t); err != nil {
		return err
	}
	_, restorationID, err := s.startRestore(ctx, snapshot, map[string]any{"type": "dimension", "region_dir_relpath": fixtureRegion})
	if err != nil {
		return err
	}
	if err = waitResticPause(ctx, t, "backup"); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "POST", "/api/snapshots", s.scopeRequest(map[string]any{"type": "world"}), nil, 423); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "POST", "/api/snapshots/restorations", s.restoreRequest(snapshot, map[string]any{"type": "world"}), nil, 423); err != nil {
		return err
	}
	if err = resumeResticBackup(ctx, t); err != nil {
		return err
	}
	if err = waitResticPause(ctx, t, "ls"); err != nil {
		return err
	}
	if _, err = backend.Docker.Run(ctx, "kill", "--signal", "KILL", backend.Name); err != nil {
		return err
	}
	if err = backend.Restart(ctx); err != nil {
		return err
	}
	var row restoration
	if err = s.client.JSON(ctx, "GET", "/api/snapshots/restorations/"+restorationID, nil, &row, 200); err != nil {
		return err
	}
	if row.Status != "interrupted" || row.Error != "server restarted before completion" || !row.SafetyExists || row.Finished == nil {
		return fmt.Errorf("restart failed to reconcile running restore: %+v", row)
	}
	if _, err = s.client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations/"+restorationID+"/rollback", nil); err != nil {
		return err
	}
	for x := range 2 {
		expected, _ := chunkPayload(regionData([2]string{"recover zero", "recover one"}), x)
		if err = s.checkChunk(ctx, x, expected); err != nil {
			return fmt.Errorf("interrupted restore rollback: %w", err)
		}
	}
	return nil
}
