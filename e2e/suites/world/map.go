package world

import (
	"bytes"
	"context"
	"fmt"
	"image/png"
	"net/url"
	"os"
	"path/filepath"
	"sync"
	"time"

	"mc-admin/e2e/internal/engine"
)

func mapRendering(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.stop(ctx); err != nil {
		return err
	}
	var layout struct {
		Roots []struct {
			Name       string `json:"name"`
			Dimensions []struct {
				Region string `json:"region_dir"`
			} `json:"dimensions"`
		} `json:"world_roots"`
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/world-restore/layout", nil, &layout, 200); err != nil {
		return err
	}
	if len(layout.Roots) == 0 || len(layout.Roots[0].Dimensions) == 0 {
		return fmt.Errorf("real Minecraft world has no discovered dimensions")
	}
	region := "world/region"
	var regions [][3]int64
	if err = s.client.JSON(ctx, "GET", s.base+"/map/regions?region="+url.QueryEscape(region), nil, &regions, 200); err != nil {
		return err
	}
	if len(regions) == 0 {
		return fmt.Errorf("saved real world has no nonempty region")
	}
	rx, rz := regions[0][0], regions[0][1]
	tile := fmt.Sprintf("%s/map/tiles/%d/%d.png?region=%s", s.base, rx, rz, region)
	if err = s.client.JSON(ctx, "GET", tile, nil, nil, 409); err != nil {
		return err
	}
	for _, invalid := range []string{"../", "/tmp", "."} {
		if err = s.client.JSON(ctx, "GET", s.base+"/map/regions?region="+url.QueryEscape(invalid), nil, nil, 400); err != nil {
			return err
		}
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/map/regions?region=missing/region", nil, nil, 404); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/map/regions", nil, nil, 422); err != nil {
		return err
	}
	for i, suffix := range []string{"", "", "?force=true"} {
		cached := 0
		if _, err = s.client.SSEEvents(ctx, "POST", s.base+"/map/initialize"+suffix, nil, "complete", func(event map[string]any) error {
			if event["cached"] == true {
				cached++
			}
			return nil
		}); err != nil {
			return err
		}
		if i == 1 && cached != 2 {
			return fmt.Errorf("second initialization reused %d prerequisites, expected client and palette", cached)
		}
		if i == 2 && cached != 0 {
			return fmt.Errorf("forced initialization unexpectedly reused prerequisites")
		}
	}
	var status struct {
		Client  bool   `json:"client_jar_present"`
		Palette bool   `json:"palette_present"`
		Current bool   `json:"palette_current"`
		Version string `json:"version"`
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/map/status", nil, &status, 200); err != nil {
		return err
	}
	if !status.Client || !status.Palette || !status.Current || status.Version == "" {
		return fmt.Errorf("map prerequisite state incomplete: %+v", status)
	}
	var wg sync.WaitGroup
	errors := make(chan error, 3)
	for range 3 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			response, err := s.client.Do(ctx, "GET", tile, nil, nil)
			if err == nil {
				err = s.client.Expect(response, 200)
			}
			if err == nil {
				image, decodeErr := png.DecodeConfig(bytes.NewReader(response.Body))
				err = decodeErr
				if err == nil && (image.Width != 512 || image.Height != 512) {
					err = fmt.Errorf("unexpected region PNG size %dx%d", image.Width, image.Height)
				}
			}
			errors <- err
		}()
	}
	wg.Wait()
	close(errors)
	for err := range errors {
		if err != nil {
			return err
		}
	}
	first, err := s.client.Do(ctx, "GET", tile, nil, nil)
	if err != nil {
		return err
	}
	if err = s.client.Expect(first, 200); err != nil {
		return err
	}
	if first.Header.Get("ETag") == "" || first.Header.Get("Cache-Control") != "private, max-age=31536000" {
		return fmt.Errorf("map tile has no freshness/cache contract")
	}
	file := filepath.Join(t.Env.Dir, "servers", s.id, "data", region, fmt.Sprintf("r.%d.%d.mca", rx, rz))
	st, err := os.Stat(file)
	if err != nil {
		return err
	}
	changed := st.ModTime().Add(2 * time.Second)
	if err = os.Chtimes(file, changed, changed); err != nil {
		return err
	}
	second, err := s.client.Do(ctx, "GET", tile, nil, nil)
	if err != nil {
		return err
	}
	if err = s.client.Expect(second, 200); err != nil {
		return err
	}
	if second.Header.Get("ETag") == first.Header.Get("ETag") {
		return fmt.Errorf("stale MCA tile did not refresh its ETag")
	}
	if !bytes.Equal(first.Body, second.Body) {
		return fmt.Errorf("unchanged terrain rendered different PNG bytes")
	}
	return s.client.JSON(ctx, "GET", s.base+"/map/tiles/999/999.png?region="+region, nil, nil, 404)
}
