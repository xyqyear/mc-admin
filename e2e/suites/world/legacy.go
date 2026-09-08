package world

import (
	"bytes"
	"compress/gzip"
	"context"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
)

func gzipNBT(data []byte) []byte {
	var result bytes.Buffer
	w := gzip.NewWriter(&result)
	_, _ = w.Write(data)
	_ = w.Close()
	return result.Bytes()
}

func legacyClaims(format string) []byte {
	var b nbt
	b.name(10, "")
	if format == "per_team_nbt" {
		b.name(10, "ClaimedChunks")
		b.name(9, "88")
		b.raw([]byte{10})
		b.number(int32(2))
		for x := range 2 {
			b.integer("x", int32(x))
			b.integer("z", 0)
			b.name(1, "loaded")
			b.raw([]byte{byte(1 - x)})
			b.raw([]byte{0})
		}
		b.raw([]byte{0})
	} else {
		b.name(10, "Data")
		b.name(10, "ftbu:data")
		b.name(10, "Chunks")
		b.name(9, playerID)
		b.raw([]byte{11})
		b.number(int32(2))
		for x := range 2 {
			b.number(int32(4))
			for _, value := range []int32{88, int32(x), 0, int32(1 - x)} {
				b.number(value)
			}
		}
		b.raw([]byte{0, 0, 0})
	}
	b.raw([]byte{0})
	return gzipNBT(b.data())
}

func legacyPlayer() []byte {
	var b nbt
	b.name(10, "")
	b.integer("Dimension", 88)
	b.name(9, "Pos")
	b.raw([]byte{6})
	b.number(int32(3))
	for _, value := range []float64{8, 64, 8} {
		b.number(value)
	}
	b.raw([]byte{0})
	return gzipNBT(b.data())
}

func legacyExtraction(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	for _, root := range []string{"world", "world_nether"} {
		if err = s.seed(root+"/level.dat", gzipNBT([]byte{10, 0, 0, 0})); err != nil {
			return err
		}
	}
	if err = s.createMarker(ctx, "server.properties", "level-name=world\n"); err != nil {
		return err
	}
	for _, region := range []string{"world/region", "world/DIM88/region", "world/dimensions/ftbteamdimensions/team/team-a/region", "world_nether/DIM-1/region"} {
		if err = s.seed(region+"/r.0.0.mca", regionData([2]string{"legacy", "legacy"})); err != nil {
			return err
		}
	}
	if err = s.config(ctx, "world", func(config map[string]any) { config["dimension_max_depth_from_world_root"] = 8 }); err != nil {
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
	if len(layout.Roots) != 2 || layout.Roots[0].Name != "world" || len(layout.Roots[0].Dimensions) != 3 || len(layout.Roots[1].Dimensions) != 1 {
		return fmt.Errorf("legacy/custom/deep/multiworld discovery mismatch: %+v", layout)
	}
	formats := []struct {
		Name, Path string
		Data       []byte
	}{
		{"latmod_json", "world/LatMod/ClaimedChunks.json", []byte(`{"88":{"22222222222242228222222222222222":[[0,0,1],[1,0]]}}`)},
		{"universe_dat", "world/data/ftb_lib/universe.dat", legacyClaims("universe_dat")},
		{"per_team_nbt", "world/serverutilities/teams/claimedchunks/e2e-team.dat", legacyClaims("per_team_nbt")},
	}
	for _, fixture := range formats {
		if err = s.seed(fixture.Path, fixture.Data); err != nil {
			return err
		}
		var response struct {
			Available bool   `json:"available"`
			Format    string `json:"detected_format"`
			Teams     []struct {
				Name     string `json:"display_name"`
				Total    int    `json:"total_chunks"`
				Clusters []struct {
					Path   string   `json:"region_dir_relpath"`
					Forced [][2]int `json:"force_loaded"`
				} `json:"clusters"`
			} `json:"teams"`
		}
		if err = s.client.JSON(ctx, "GET", s.base+"/claims", nil, &response, 200); err != nil {
			return err
		}
		if !response.Available || response.Format != fixture.Name || len(response.Teams) != 1 {
			return fmt.Errorf("%s extraction/detection mismatch: %+v", fixture.Name, response)
		}
		team := response.Teams[0]
		if team.Name == "" || team.Total != 2 || len(team.Clusters) != 1 || team.Clusters[0].Path != "world/DIM88/region" || len(team.Clusters[0].Forced) != 1 {
			return fmt.Errorf("%s claim content/legacy dimension mismatch: %+v", fixture.Name, response)
		}
	}
	if err = s.seed("world/players/legacybuilder.dat", legacyPlayer()); err != nil {
		return err
	}
	if err = s.seed("world/playerdata/"+playerID+".dat", gzipNBT([]byte{10, 0, 0, 0})); err != nil {
		return err
	}
	var players struct {
		Players []struct {
			ID      string `json:"id"`
			Kind    string `json:"id_kind"`
			Storage string `json:"storage"`
			Path    string `json:"region_dir_relpath"`
		} `json:"players"`
		Skipped []struct {
			Reason string `json:"reason"`
		} `json:"skipped"`
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/player-locations", nil, &players, 200); err != nil {
		return err
	}
	if len(players.Players) != 1 || players.Players[0].ID != "legacybuilder" || players.Players[0].Kind != "name" || players.Players[0].Storage != "legacy_players" || players.Players[0].Path != "world/DIM88/region" || len(players.Skipped) != 1 || players.Skipped[0].Reason != "missing_pos" {
		return fmt.Errorf("legacy player location/missing fields mismatch: %+v", players)
	}
	for _, endpoint := range []string{"world-restore/layout", "world-restore/dimension-labels", "claims", "player-locations", "map/status", "chunk-prune/settings", "chunk-prune/state"} {
		if err = s.client.JSON(ctx, "GET", strings.Replace(s.base, s.id, "e2e-absent", 1)+"/"+endpoint, nil, nil, 404); err != nil {
			return err
		}
	}
	return nil
}
