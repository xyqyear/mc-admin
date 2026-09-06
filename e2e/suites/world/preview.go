package world

import (
	"bytes"
	"context"
	"fmt"
	"image/png"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func previewLifecycle(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.stop(ctx); err != nil {
		return err
	}
	var regions [][3]int64
	if err = s.client.JSON(ctx, "GET", s.base+"/map/regions?region=world/region", nil, &regions, 200); err != nil {
		return err
	}
	if len(regions) == 0 {
		return fmt.Errorf("generated world has no region to preview")
	}
	rx, rz := regions[0][0], regions[0][1]
	snapshot, err := s.snapshot(ctx, map[string]any{"type": "world"})
	if err != nil {
		return err
	}
	if _, err = s.client.SSE(ctx, "POST", s.base+"/map/initialize", nil, "complete"); err != nil {
		return err
	}
	selection := map[string]any{"type": "regions", "region_dir_relpath": "world/region", "regions": [][2]int64{{rx, rz}}}
	preview, err := s.client.SSE(ctx, "POST", s.base+"/world-restore/preview", request(snapshot, selection), "ready")
	if err != nil {
		return err
	}
	session, _ := preview["session_id"].(string)
	if session == "" {
		return fmt.Errorf("preview returned no session")
	}
	path := s.base + "/world-restore/preview/" + session
	if err = s.client.JSON(ctx, "POST", path+"/heartbeat", nil, nil, 204); err != nil {
		return err
	}
	tile := fmt.Sprintf("%s/tile/%d/%d.png", path, rx, rz)
	response, err := s.client.Do(ctx, "GET", tile, nil, nil)
	if err != nil {
		return err
	}
	if err = s.client.Expect(response, 200); err != nil {
		return err
	}
	if _, err = png.DecodeConfig(bytes.NewReader(response.Body)); err != nil {
		return fmt.Errorf("preview tile is not a PNG: %w", err)
	}
	if response.Header.Get("Cache-Control") != "private, max-age=60" {
		return fmt.Errorf("preview tile uses wrong cache policy")
	}
	cached, err := s.client.Do(ctx, "GET", tile, nil, nil)
	if err != nil {
		return err
	}
	if err = s.client.Expect(cached, 200); err != nil {
		return err
	}
	if !bytes.Equal(response.Body, cached.Body) {
		return fmt.Errorf("same preview tile changed")
	}
	if err = s.client.JSON(ctx, "GET", path+"/tile/999/999.png", nil, nil, 404); err != nil {
		return err
	}
	second, err := s.client.SSE(ctx, "POST", s.base+"/world-restore/preview", request(snapshot, selection), "ready")
	if err != nil {
		return err
	}
	secondID, _ := second["session_id"].(string)
	if secondID == session || secondID == "" {
		return fmt.Errorf("replacement preview reused prior session ID")
	}
	if err = s.client.JSON(ctx, "POST", path+"/heartbeat", nil, nil, 404); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "GET", tile, nil, nil, 404); err != nil {
		return err
	}
	for range 2 {
		if err = s.client.JSON(ctx, "DELETE", s.base+"/world-restore/preview/"+secondID, nil, nil, 204); err != nil {
			return err
		}
	}
	if err = s.config(ctx, "snapshots", func(config map[string]any) {
		settings := config["world_restore"].(map[string]any)
		settings["preview_avg_region_bytes"] = int64(1) << 60
	}); err != nil {
		return err
	}
	_, err = s.client.SSE(ctx, "POST", s.base+"/world-restore/preview", request(snapshot, selection), "ready")
	if err == nil || !strings.Contains(err.Error(), "insufficient disk for preview") {
		return fmt.Errorf("preview disk guard did not reject capacity requirement: %v", err)
	}
	if err = s.config(ctx, "snapshots", func(config map[string]any) {
		settings := config["world_restore"].(map[string]any)
		settings["preview_avg_region_bytes"] = 1
		settings["preview_session_ttl_seconds"] = 60
		settings["preview_janitor_interval_seconds"] = 10
	}); err != nil {
		return err
	}
	expiring, err := s.client.SSE(ctx, "POST", s.base+"/world-restore/preview", request(snapshot, selection), "ready")
	if err != nil {
		return err
	}
	expiringID, _ := expiring["session_id"].(string)
	// Every tile/heartbeat API extends TTL, so observe owned staging removal before the final API assertion.
	waitCtx, cancel := context.WithTimeout(ctx, 140*time.Second)
	defer cancel()
	backend := fixtures.BackendOf(t.Env)
	if err = api.Wait(waitCtx, 2*time.Second, "preview janitor deletes expired owned session", func(ctx context.Context) (bool, error) {
		output, err := backend.Docker.Run(ctx, "exec", backend.Name, "sh", "-c", `if test -d "$1"; then echo present; else echo absent; fi`, "--", "/tmp/mc-admin-world-restore/"+expiringID)
		if err != nil {
			return false, api.Permanent(err)
		}
		return strings.TrimSpace(output) == "absent", nil
	}); err != nil {
		return err
	}
	return s.client.JSON(ctx, "POST", s.base+"/world-restore/preview/"+expiringID+"/heartbeat", nil, nil, 404)
}
