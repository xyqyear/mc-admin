package world

import (
	"bytes"
	"context"
	"fmt"
	"net/url"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func emptyScopeRollback(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.seedStoppedWorld(); err != nil {
		return err
	}
	selected := fixtureRegion + "/r.0.0.mca"
	neighbor := fixtureRegion + "/r.1.0.mca"
	if err = s.client.JSON(ctx, "DELETE", s.base+"/files?path="+url.QueryEscape("/"+selected), nil, nil, 200); err != nil {
		return err
	}
	var backup struct {
		Snapshot struct {
			ID string `json:"id"`
		} `json:"snapshot"`
	}
	if err = s.client.JSON(ctx, "POST", "/api/snapshots", map[string]any{"server_id": s.id, "paths": []string{"/world"}}, &backup, 200); err != nil {
		return err
	}
	if backup.Snapshot.ID == "" {
		return fmt.Errorf("empty world snapshot returned no ID")
	}
	if err = s.seed("plugins/ordinary.txt", []byte("outside world restoration")); err != nil {
		return err
	}
	live := regionData([2]string{"live selected zero", "live selected one"})
	other := regionData([2]string{"live neighbor zero", "live neighbor one"})
	for _, kind := range []string{"dimension", "regions"} {
		if err = t.Step(kind+" empty-scope restore and two reversible history operations", func() error {
			if err := s.seed(selected, live); err != nil {
				return err
			}
			if err := s.seed(neighbor, other); err != nil {
				return err
			}
			selection := map[string]any{"type": kind, "region_dir_relpath": fixtureRegion}
			if kind == "regions" {
				selection["regions"] = [][2]int{{0, 0}}
			}
			check := func(empty bool) error {
				for _, file := range []struct {
					path    string
					payload []byte
				}{
					{selected, live}, {neighbor, other},
				} {
					if empty && (file.path == selected || kind == "dimension") {
						if err := s.client.JSON(ctx, "GET", s.base+"/files/download?path="+url.QueryEscape("/"+file.path), nil, nil, 404); err != nil {
							return fmt.Errorf("empty scope retained %s: %w", file.path, err)
						}
					} else {
						payload, err := s.download(ctx, file.path)
						if err != nil {
							return err
						}
						if !bytes.Equal(payload, file.payload) {
							return fmt.Errorf("%s history changed unselected or restored bytes in %s", kind, file.path)
						}
					}
				}
				return fixtures.CheckFile(ctx, s.client, s.id, "/plugins/ordinary.txt", "outside world restoration")
			}
			path := s.base + "/world-restore/restore"
			var body any = request(backup.Snapshot.ID, selection)
			for index := range 3 {
				complete, err := s.client.SSE(ctx, "POST", path, body, "complete")
				if err != nil {
					return err
				}
				id, _ := complete["restoration_id"].(string)
				if id == "" {
					return fmt.Errorf("%s history operation %d omitted restoration ID", kind, index)
				}
				var history restoration
				if err := s.client.JSON(ctx, "GET", s.base+"/world-restore/restorations/"+id, nil, &history, 200); err != nil {
					return err
				}
				if history.Status != "succeeded" || !history.SafetyExists || history.Rollback != (index > 0) {
					return fmt.Errorf("%s empty-scope history operation %d is incomplete: %+v", kind, index, history)
				}
				if err := check(index != 1); err != nil {
					return err
				}
				path = s.base + "/world-restore/restorations/" + id + "/rollback"
				body = nil
			}
			return nil
		}); err != nil {
			return err
		}
	}
	return nil
}
