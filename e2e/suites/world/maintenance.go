package world

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net/url"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
)

func missingSidecars(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.stop(ctx); err != nil {
		return err
	}
	markers := [2]string{"sidecar zero", "sidecar one"}
	if err = s.seedRegion(markers); err != nil {
		return err
	}
	directories := []string{"world/dimensions/e2e/testing/entities", "world/dimensions/e2e/testing/poi"}
	for _, directory := range directories {
		if err = s.seed(directory+"/r.0.0.mca", regionData(markers)); err != nil {
			return err
		}
	}
	snapshot, err := s.snapshot(ctx, map[string]any{"type": "world"})
	if err != nil {
		return err
	}
	for _, directory := range directories {
		if err = s.client.JSON(ctx, "DELETE", s.base+"/files?path="+url.QueryEscape("/"+directory), nil, nil, 200); err != nil {
			return err
		}
	}
	for _, kind := range []string{"dimension", "regions", "chunks"} {
		selection := map[string]any{"type": kind, "region_dir_relpath": fixtureRegion}
		if kind == "regions" {
			selection["regions"] = [][2]int{{0, 0}}
		}
		if kind == "chunks" {
			selection["chunks"] = [][2]int{{0, 0}}
		}
		complete, err := s.client.SSE(ctx, "POST", s.base+"/world-restore/restore", request(snapshot, selection), "complete")
		if err != nil {
			return err
		}
		for _, directory := range directories {
			data, err := s.download(ctx, directory+"/r.0.0.mca")
			if err != nil {
				return err
			}
			actual, err := chunkPayload(data, 0)
			if err != nil {
				return err
			}
			expected, _ := chunkPayload(regionData(markers), 0)
			if !bytes.Equal(actual, expected) {
				return fmt.Errorf("%s restore omitted missing %s payload", kind, directory)
			}
		}
		id, _ := complete["restoration_id"].(string)
		if _, err = s.client.SSE(ctx, "POST", s.base+"/world-restore/restorations/"+id+"/rollback", nil, "complete"); err != nil {
			return err
		}
		var listing struct {
			Items []struct {
				Name string `json:"name"`
			} `json:"items"`
		}
		if err = s.client.JSON(ctx, "GET", s.base+"/files?path="+url.QueryEscape("/world/dimensions/e2e/testing"), nil, &listing, 200); err != nil {
			return err
		}
		for _, item := range listing.Items {
			if item.Name == "entities" || item.Name == "poi" {
				return fmt.Errorf("%s rollback did not restore %s directory absence", kind, item.Name)
			}
		}
	}
	return nil
}

func disconnectedRestore(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.createMarker(ctx, "e2e-online.txt", "before online restore"); err != nil {
		return err
	}
	var fileSnapshot struct {
		Snapshot struct {
			ID string `json:"id"`
		} `json:"snapshot"`
	}
	fileTarget := map[string]any{"server_id": s.id, "paths": []string{"/e2e-online.txt"}}
	if err = s.client.JSON(ctx, "POST", "/api/snapshots", fileTarget, &fileSnapshot, 200); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "POST", s.base+"/files/content?path=/e2e-online.txt", map[string]any{"content": "changed online"}, nil, 200); err != nil {
		return err
	}
	if _, err = s.client.SSE(ctx, "POST", "/api/snapshots/restore", map[string]any{"server_id": s.id, "paths": []string{"/e2e-online.txt"}, "snapshot_id": fileSnapshot.Snapshot.ID}, "complete"); err != nil {
		return fmt.Errorf("ordinary file restore must remain available online: %w", err)
	}
	online, err := s.download(ctx, "e2e-online.txt")
	if err != nil || string(online) != "before online restore" {
		return fmt.Errorf("online file restore did not restore contents: %q: %w", online, err)
	}
	if err = s.client.JSON(ctx, "POST", "/api/snapshots/restore", map[string]any{"server_id": s.id, "paths": []string{"/"}, "snapshot_id": fileSnapshot.Snapshot.ID}, nil, 409); err != nil {
		return err
	}
	if err = s.stop(ctx); err != nil {
		return err
	}
	before := [2]string{"before disconnect", "before disconnect neighbor"}
	if err = s.seedRegion(before); err != nil {
		return err
	}
	snapshot, err := s.snapshot(ctx, map[string]any{"type": "dimension", "region_dir_relpath": fixtureRegion})
	if err != nil {
		return err
	}
	after := [2]string{"recover disconnect", "recover disconnect neighbor"}
	if err = s.seedRegion(after); err != nil {
		return err
	}
	if err = startResticPauses(ctx, t); err != nil {
		return err
	}
	disconnect := errors.New("close restore response after persisted start")
	id := ""
	_, err = s.client.SSEEvents(ctx, "POST", s.base+"/world-restore/restore", request(snapshot, map[string]any{"type": "dimension", "region_dir_relpath": fixtureRegion}), "complete", func(event map[string]any) error {
		if event["event_type"] == "start" {
			if err := waitResticPause(ctx, t, "backup"); err != nil {
				return err
			}
			var maintenance struct {
				Active bool `json:"active"`
			}
			if err := s.client.JSON(ctx, "GET", s.base+"/maintenance", nil, &maintenance, 200); err != nil {
				return err
			}
			if !maintenance.Active {
				return fmt.Errorf("restore does not advertise active maintenance")
			}
			if err := s.client.JSON(ctx, "POST", s.base+"/operations", map[string]any{"action": "start"}, nil, 423); err != nil {
				return err
			}
			if err := s.client.JSON(ctx, "POST", "/api/snapshots", map[string]any{}, nil, 423); err != nil {
				return err
			}
			return resumeResticBackup(ctx, t)
		}
		if event["event_type"] == "restore" {
			if err := waitResticPause(ctx, t, "ls"); err != nil {
				return err
			}
			id, _ = event["restoration_id"].(string)
			return disconnect
		}
		return nil
	})
	if !errors.Is(err, disconnect) || id == "" {
		return fmt.Errorf("restore did not reach disconnection point: %w", err)
	}
	if err = api.Wait(ctx, 100*time.Millisecond, "disconnected restore finishes cleanup", func(ctx context.Context) (bool, error) {
		var row restoration
		if err := s.client.JSON(ctx, "GET", s.base+"/world-restore/restorations/"+id, nil, &row, 200); err != nil {
			return false, api.Permanent(err)
		}
		if row.Status == "running" {
			return false, nil
		}
		if row.Status != "interrupted" || row.Finished == nil || !row.SafetyExists {
			return false, api.Permanent(fmt.Errorf("disconnected restore has inconsistent terminal state: %+v", row))
		}
		var maintenance struct {
			Active bool `json:"active"`
		}
		if err := s.client.JSON(ctx, "GET", s.base+"/maintenance", nil, &maintenance, 200); err != nil {
			return false, api.Permanent(err)
		}
		return !maintenance.Active, nil
	}); err != nil {
		return err
	}
	if _, err = s.client.SSE(ctx, "POST", s.base+"/world-restore/restorations/"+id+"/rollback", nil, "complete"); err != nil {
		return err
	}
	for x := range 2 {
		expected, _ := chunkPayload(regionData(after), x)
		if err = s.checkChunk(ctx, x, expected); err != nil {
			return err
		}
	}
	return nil
}
