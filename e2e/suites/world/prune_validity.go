package world

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type pruneState struct {
	PreviewTask *api.Task `json:"preview_task"`
	ApplyTask   *api.Task `json:"apply_task"`
	Preview     *struct {
		ID           string    `json:"task_id"`
		InputVersion string    `json:"input_version"`
		Expires      time.Time `json:"expires_at"`
		Availability string    `json:"availability"`
		ApplyID      *string   `json:"apply_task_id"`
	} `json:"preview"`
}

func (s *scenario) seedStoppedWorld() error {
	if err := s.seed("world/level.dat", gzipNBT([]byte{10, 0, 0, 0})); err != nil {
		return err
	}
	if err := s.seed("server.properties", []byte("level-name=world\n")); err != nil {
		return err
	}
	return s.seedRegion([2]string{"claimed", "unclaimed"})
}

func (s *scenario) pruneState(ctx context.Context, previewID string) (pruneState, error) {
	var result pruneState
	if err := s.client.JSON(ctx, "GET", s.base+"/chunk-prune/state", nil, &result, 200); err != nil {
		return result, err
	}
	if result.Preview == nil || result.Preview.ID != previewID || result.Preview.InputVersion == "" || result.Preview.Expires.IsZero() || result.Preview.Availability == "" {
		return result, fmt.Errorf("prune preview has no usable identity/lifetime: %+v", result.Preview)
	}
	return result, nil
}

func (s *scenario) pruneConflict(ctx context.Context, previewID, code string) error {
	return s.conflict(ctx, s.base+"/chunk-prune/apply", map[string]string{"preview_task_id": previewID}, code)
}

func (s *scenario) conflict(ctx context.Context, path string, body any, code string) error {
	var result struct {
		Detail struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		} `json:"detail"`
	}
	if err := s.client.JSON(ctx, "POST", path, body, &result, 409); err != nil {
		return err
	}
	if result.Detail.Code != code || result.Detail.Message == "" {
		return fmt.Errorf("expected actionable %s conflict, received %+v", code, result.Detail)
	}
	return nil
}

func prunePreviewValidity(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	version, err := backend.Docker.Run(ctx, "exec", backend.Name, "mcmap", "--version")
	if err != nil {
		return err
	}
	if strings.TrimSpace(version) != "mcmap 0.8.4" {
		return fmt.Errorf("prune qualification requires mcmap 0.8.4, received %q", version)
	}
	t.Recorder.Event("adapter_version", map[string]string{"tool": "mcmap", "version": strings.TrimSpace(version)})
	if err = s.seedStoppedWorld(); err != nil {
		return err
	}
	if err = s.claims(); err != nil {
		return err
	}
	if err = t.Step("world and claim changes invalidate a completed dry run without deleting chunks", func() error {
		for _, change := range []string{"world", "claims"} {
			preview, err := s.prunePreview(ctx, "chunks", 3600)
			if err != nil {
				return err
			}
			if _, err = s.pruneState(ctx, preview.ID); err != nil {
				return err
			}
			if change == "world" {
				err = s.seedRegion([2]string{"modified claimed", "modified unclaimed"})
			} else {
				err = s.seed("world/ftbchunks/"+teamID+".snbt", []byte(`{chunks: {"e2e:testing": [{x: 0, z: 0, force_loaded: 1b}, {x: 1, z: 0, force_loaded: 0b}]}}`))
			}
			if err != nil {
				return err
			}
			if err = s.pruneConflict(ctx, preview.ID, "prune_preview_stale"); err != nil {
				return err
			}
			for x := range 2 {
				expected, _ := chunkPayload(regionData([2]string{"modified claimed", "modified unclaimed"}), x)
				if err = s.checkChunk(ctx, x, expected); err != nil {
					return fmt.Errorf("stale %s preview changed live data: %w", change, err)
				}
			}
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("a naturally expired preview requires a new dry run", func() error {
		if err := s.config(ctx, "mcmap", func(config map[string]any) { config["prune_preview_ttl_seconds"] = 1 }); err != nil {
			return err
		}
		preview, err := s.prunePreview(ctx, "chunks", 3600)
		if err != nil {
			return err
		}
		state, err := s.pruneState(ctx, preview.ID)
		if err != nil {
			return err
		}
		if err = api.Wait(ctx, 100*time.Millisecond, "prune preview TTL elapses", func(context.Context) (bool, error) {
			return time.Now().After(state.Preview.Expires.Add(100 * time.Millisecond)), nil
		}); err != nil {
			return err
		}
		return s.pruneConflict(ctx, preview.ID, "prune_preview_expired")
	}); err != nil {
		return err
	}
	if err = s.config(ctx, "mcmap", func(config map[string]any) { config["prune_preview_ttl_seconds"] = 1800 }); err != nil {
		return err
	}
	if err = s.claims(); err != nil {
		return err
	}
	preview, err := s.prunePreview(ctx, "chunks", 3600)
	if err != nil {
		return err
	}
	var started struct {
		ID string `json:"task_id"`
	}
	if err = s.client.JSON(ctx, "POST", s.base+"/chunk-prune/apply", map[string]string{"preview_task_id": preview.ID}, &started, 200); err != nil {
		return err
	}
	if _, err = s.client.Task(ctx, started.ID); err != nil {
		return err
	}
	if err = s.pruneConflict(ctx, preview.ID, "prune_preview_consumed"); err != nil {
		return err
	}
	state, err := s.pruneState(ctx, preview.ID)
	if err != nil {
		return err
	}
	if state.Preview.Availability != "consumed" || state.Preview.ApplyID == nil || *state.Preview.ApplyID != started.ID {
		return fmt.Errorf("consumed preview lost its single apply identity: %+v", state.Preview)
	}
	claimed, _ := chunkPayload(regionData([2]string{"modified claimed", "modified unclaimed"}), 0)
	if err = s.checkChunk(ctx, 0, claimed); err != nil {
		return err
	}
	if err = s.checkChunk(ctx, 1, nil); err != nil {
		return err
	}
	return fixtures.Status(ctx, s.client, s.id, "exists")
}
