package world

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
)

func (s *scenario) prunePreview(ctx context.Context, mode string, threshold int) (api.Task, error) {
	var start struct {
		ID string `json:"task_id"`
	}
	if err := s.client.JSON(ctx, "POST", s.base+"/chunk-prune/preview", map[string]any{"mode": mode, "threshold_seconds": threshold}, &start, 200); err != nil {
		return api.Task{}, err
	}
	return s.client.Task(ctx, start.ID)
}

func chunkPrune(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	var settings struct {
		Threshold int `json:"default_threshold_seconds"`
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/chunk-prune/settings", nil, &settings, 200); err != nil {
		return err
	}
	if settings.Threshold < 0 {
		return fmt.Errorf("negative prune default")
	}
	var state struct {
		Preview *api.Task `json:"preview_task"`
		Apply   *api.Task `json:"apply_task"`
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/chunk-prune/state", nil, &state, 200); err != nil {
		return err
	}
	if state.Preview != nil || state.Apply != nil {
		return fmt.Errorf("fresh server contains prune task history")
	}
	if err = s.client.JSON(ctx, "POST", s.base+"/chunk-prune/preview", map[string]any{"mode": "chunks", "threshold_seconds": -1}, nil, 422); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "POST", s.base+"/chunk-prune/apply", map[string]any{"preview_task_id": "missing"}, nil, 404); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/chunk-prune/previews/missing/geometry", nil, nil, 404); err != nil {
		return err
	}
	running, err := s.prunePreview(ctx, "chunks", 0)
	if err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "POST", s.base+"/chunk-prune/apply", map[string]any{"preview_task_id": running.ID}, nil, 409); err != nil {
		return err
	}
	if err = s.stop(ctx); err != nil {
		return err
	}
	if err = s.claims(); err != nil {
		return err
	}
	for _, mode := range []string{"chunks", "regions"} {
		if err = s.seedRegion([2]string{"claimed", "unclaimed"}); err != nil {
			return err
		}
		if err = s.seed(fixtureRegion+"/r.1.0.mca", regionData([2]string{"unclaimed region zero", "unclaimed region one"})); err != nil {
			return err
		}
		preview, err := s.prunePreview(ctx, mode, 3600)
		if err != nil {
			return err
		}
		if preview.Result["dry_run"] != true {
			return fmt.Errorf("prune preview is not a dry run: %+v", preview.Result)
		}
		var geometry struct {
			Mode       string `json:"mode"`
			Ticks      int    `json:"threshold_ticks"`
			Dimensions []struct {
				Path   string `json:"region_dir_relpath"`
				Unit   string `json:"unit"`
				Count  int    `json:"cell_count"`
				Shapes []struct {
					Cells int       `json:"cell_count"`
					Rings [][][]int `json:"rings"`
				} `json:"shapes"`
			} `json:"dimensions"`
		}
		if err = s.client.JSON(ctx, "GET", s.base+"/chunk-prune/previews/"+preview.ID+"/geometry", nil, &geometry, 200); err != nil {
			return err
		}
		if geometry.Mode != mode || geometry.Ticks != 72000 {
			return fmt.Errorf("preview geometry threshold/mode mismatch")
		}
		found := false
		for _, dimension := range geometry.Dimensions {
			if dimension.Path != fixtureRegion {
				continue
			}
			found = true
			expected, unit := 3, "chunk"
			if mode == "regions" {
				expected, unit = 1, "region"
			}
			if dimension.Count != expected || dimension.Unit != unit || len(dimension.Shapes) == 0 {
				return fmt.Errorf("%s claimed selection geometry: %+v", mode, dimension)
			}
			for _, shape := range dimension.Shapes {
				if len(shape.Rings) == 0 || len(shape.Rings[0]) < 4 {
					return fmt.Errorf("preview geometry has no boundary polygon")
				}
			}
		}
		if !found {
			return fmt.Errorf("prune geometry omitted seeded dimension")
		}
		for x := range 2 {
			expected, _ := chunkPayload(regionData([2]string{"claimed", "unclaimed"}), x)
			if err = s.checkChunk(ctx, x, expected); err != nil {
				return fmt.Errorf("prune preview mutated live world: %w", err)
			}
		}
		var started struct {
			ID string `json:"task_id"`
		}
		if err = s.client.JSON(ctx, "POST", s.base+"/chunk-prune/apply", map[string]any{"preview_task_id": preview.ID}, &started, 200); err != nil {
			return err
		}
		applied, err := s.client.Task(ctx, started.ID)
		if err != nil {
			return err
		}
		if applied.Result["dry_run"] != false {
			return fmt.Errorf("prune apply reported dry run")
		}
		claimed, _ := chunkPayload(regionData([2]string{"claimed", "unclaimed"}), 0)
		if err = s.checkChunk(ctx, 0, claimed); err != nil {
			return fmt.Errorf("prune removed claimed chunk: %w", err)
		}
		var unclaimed []byte
		if mode == "regions" {
			unclaimed, _ = chunkPayload(regionData([2]string{"claimed", "unclaimed"}), 1)
		}
		if err = s.checkChunk(ctx, 1, unclaimed); err != nil {
			return fmt.Errorf("prune mode boundary: %w", err)
		}
		empty, err := s.download(ctx, fixtureRegion+"/r.1.0.mca")
		if err != nil {
			return err
		}
		for x := range 2 {
			payload, err := chunkPayload(empty, x)
			if err != nil {
				return err
			}
			if len(payload) != 0 {
				return fmt.Errorf("unclaimed region still contains chunk %d", x)
			}
		}
		if err = s.client.JSON(ctx, "GET", s.base+"/chunk-prune/state", nil, &state, 200); err != nil {
			return err
		}
		if state.Preview == nil || state.Preview.ID != preview.ID || state.Apply == nil || state.Apply.ID != applied.ID {
			return fmt.Errorf("prune latest task state is inconsistent")
		}
	}
	for index := 2; index < 258; index++ {
		if err = s.seed(fmt.Sprintf("%s/r.%d.0.mca", fixtureRegion, index), regionData([2]string{"cancel", "cancel"})); err != nil {
			return err
		}
	}
	var cancelTask struct {
		ID string `json:"task_id"`
	}
	if err = s.client.JSON(ctx, "POST", s.base+"/chunk-prune/preview", map[string]any{"mode": "chunks", "threshold_seconds": 1}, &cancelTask, 200); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "POST", "/api/tasks/"+cancelTask.ID+"/cancel", nil, nil, 200); err != nil {
		return err
	}
	return api.Wait(ctx, 100*time.Millisecond, "prune cancellation terminates worker", func(ctx context.Context) (bool, error) {
		var task api.Task
		if err := s.client.JSON(ctx, "GET", "/api/tasks/"+cancelTask.ID, nil, &task, 200); err != nil {
			return false, api.Permanent(err)
		}
		if strings.EqualFold(task.Status, "cancelled") {
			return true, nil
		}
		if strings.EqualFold(task.Status, "failed") || strings.EqualFold(task.Status, "completed") {
			return false, api.Permanent(fmt.Errorf("cancelled prune ended %s", task.Status))
		}
		return false, nil
	})
}
