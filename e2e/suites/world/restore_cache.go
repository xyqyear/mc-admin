package world

import (
	"bytes"
	"context"
	"crypto/sha256"
	"fmt"
	"image/png"
	"os"
	"path/filepath"
)

func (s *scenario) prepareRestoreCacheCheck(ctx context.Context) (func() error, error) {
	var regions [][3]int64
	if err := s.client.JSON(ctx, "GET", s.base+"/map/regions?region=world/region", nil, &regions, 200); err != nil {
		return nil, err
	}
	if len(regions) < 2 {
		return nil, fmt.Errorf("cache recovery needs two saved real Minecraft regions, got %d", len(regions))
	}
	data := filepath.Join(s.t.Env.Dir, "servers", s.id, "data")
	tiles := make([]string, 2)
	var original []byte
	endpoint := ""
	for index, region := range regions[:2] {
		url := fmt.Sprintf("%s/map/tiles/%d/%d.png?region=world/region", s.base, region[0], region[1])
		response, err := s.client.Do(ctx, "GET", url, nil, nil)
		if err != nil {
			return nil, err
		}
		if err = s.client.Expect(response, 200); err != nil {
			return nil, err
		}
		tiles[index] = filepath.Join(data, ".mcmap", "tiles", "world", "region", fmt.Sprintf("r.%d.%d.png", region[0], region[1]))
		if index == 0 {
			original, endpoint = response.Body, url
		}
	}
	retained := map[string][32]byte{}
	for _, path := range []string{tiles[1], filepath.Join(data, ".mcmap", "palette.json"), filepath.Join(data, ".mcmap", "client.jar")} {
		contents, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		retained[path] = sha256.Sum256(contents)
	}
	region := regions[0]
	mca := filepath.Join(data, "world", "region", fmt.Sprintf("r.%d.%d.mca", region[0], region[1]))
	contents, err := os.ReadFile(mca)
	if err != nil {
		return nil, err
	}
	// Unreferenced padding changes the file without inventing terrain for the real renderer.
	if err = os.WriteFile(mca, append(contents, make([]byte, 4096)...), 0o644); err != nil {
		return nil, err
	}
	return func() error {
		if _, err := os.Stat(tiles[0]); !os.IsNotExist(err) {
			return fmt.Errorf("restored terrain kept a stale cached tile: %v", err)
		}
		for path, digest := range retained {
			contents, err := os.ReadFile(path)
			if err != nil || sha256.Sum256(contents) != digest {
				return fmt.Errorf("recovery changed unrelated cache or rendering prerequisite %s: %v", filepath.Base(path), err)
			}
		}
		response, err := s.client.Do(ctx, "GET", endpoint, nil, nil)
		if err != nil {
			return err
		}
		if err = s.client.Expect(response, 200); err != nil {
			return err
		}
		image, err := png.DecodeConfig(bytes.NewReader(response.Body))
		if err != nil || image.Width != 512 || image.Height != 512 || !bytes.Equal(response.Body, original) {
			return fmt.Errorf("recovered real terrain did not regenerate its original 512x512 tile: %v", err)
		}
		stored, err := os.ReadFile(tiles[0])
		if err != nil || !bytes.Equal(stored, response.Body) {
			return fmt.Errorf("regenerated tile was not stored in the owned cache: %v", err)
		}
		return nil
	}, nil
}
