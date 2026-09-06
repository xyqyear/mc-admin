package world

import (
	"context"
	"fmt"
	"reflect"

	"mc-admin/e2e/internal/engine"
)

func extraction(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.stop(ctx); err != nil {
		return err
	}
	var empty struct {
		Available bool `json:"available"`
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/claims", nil, &empty, 200); err != nil {
		return err
	}
	if empty.Available {
		return fmt.Errorf("unmodified vanilla world reported FTB claims")
	}
	if err = s.seedRegion([2]string{"claimed", "unclaimed"}); err != nil {
		return err
	}
	if err = s.claims(); err != nil {
		return err
	}
	if err = s.seed("world/ftbchunks/"+teamID+".snbt", []byte(`{chunks: {"e2e:testing": [{x: 0, z: 0, force_loaded: 1b},{x: 1, z: 0},{x: 10,z: 10}], "e2e:absent": [{x: -1,z: -1}]}}`)); err != nil {
		return err
	}
	var claims struct {
		Available bool   `json:"available"`
		Format    string `json:"detected_format"`
		Teams     []struct {
			ID       string `json:"id"`
			Name     string `json:"display_name"`
			Total    int    `json:"total_chunks"`
			Clusters []struct {
				ID       string     `json:"id"`
				Region   *string    `json:"region_dir_relpath"`
				Chunks   [][2]int   `json:"chunks"`
				Forced   [][2]int   `json:"force_loaded"`
				Centroid [2]float64 `json:"centroid_block"`
			} `json:"clusters"`
		} `json:"teams"`
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/world-restore/claims", nil, &claims, 200); err != nil {
		return err
	}
	if !claims.Available || claims.Format != "snbt" || len(claims.Teams) != 1 || claims.Teams[0].Name != "E2E builders" || claims.Teams[0].Total != 4 || len(claims.Teams[0].Clusters) != 3 {
		return fmt.Errorf("FTB extraction/clustering returned unexpected result: %+v", claims)
	}
	forced := 0
	unresolved := 0
	for _, cluster := range claims.Teams[0].Clusters {
		forced += len(cluster.Forced)
		if cluster.Region == nil {
			unresolved++
		} else if *cluster.Region != fixtureRegion {
			return fmt.Errorf("FTB dimension mapped to %q", *cluster.Region)
		}
	}
	if forced != 1 || unresolved != 1 {
		return fmt.Errorf("FTB forced=%d unresolved=%d", forced, unresolved)
	}
	copy := claims
	if err = s.client.JSON(ctx, "GET", s.base+"/claims", nil, &copy, 200); err != nil {
		return err
	}
	if !reflect.DeepEqual(copy, claims) {
		return fmt.Errorf("claims alias or cluster IDs are unstable")
	}
	if err = s.seed("world/playerdata/"+playerID+".dat", playerNBT("e2e:testing")); err != nil {
		return err
	}
	if err = s.seed("world/playerdata/33333333-3333-4333-8333-333333333333.dat", playerNBT("e2e:absent")); err != nil {
		return err
	}
	if err = s.seed("world/playerdata/44444444-4444-4444-8444-444444444444.dat", []byte("not NBT")); err != nil {
		return err
	}
	var locations struct {
		Players []struct {
			UUID      string                    `json:"uuid"`
			Dimension string                    `json:"dimension_id"`
			Region    *string                   `json:"region_dir_relpath"`
			Pos       struct{ X, Y, Z float64 } `json:"pos"`
		} `json:"players"`
		Skipped []struct {
			Reason string `json:"reason"`
		} `json:"skipped"`
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/world-restore/player-locations", nil, &locations, 200); err != nil {
		return err
	}
	if len(locations.Players) != 2 || len(locations.Skipped) != 1 || locations.Skipped[0].Reason != "parse_error" {
		return fmt.Errorf("saved player extraction lost valid or invalid files: %+v", locations)
	}
	for _, player := range locations.Players {
		if player.Pos.X != 24.5 || player.Pos.Y != 65 || player.Pos.Z != -8.25 {
			return fmt.Errorf("saved position changed: %+v", player)
		}
		if player.Dimension == "e2e:testing" && (player.Region == nil || *player.Region != fixtureRegion) {
			return fmt.Errorf("saved player dimension is unresolved")
		}
		if player.Dimension == "e2e:absent" && player.Region != nil {
			return fmt.Errorf("absent dimension was resolved")
		}
	}
	other := locations
	if err = s.client.JSON(ctx, "GET", s.base+"/player-locations", nil, &other, 200); err != nil {
		return err
	}
	if !reflect.DeepEqual(other, locations) {
		return fmt.Errorf("player location alias differs")
	}
	if err = s.config(ctx, "world", func(config map[string]any) {
		config["dimension_labels"] = map[string]string{"dimensions/e2e/testing": "E2E dimension"}
	}); err != nil {
		return err
	}
	var labels struct {
		Labels map[string]string `json:"dimension_labels"`
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/world-restore/dimension-labels", nil, &labels, 200); err != nil {
		return err
	}
	if labels.Labels["dimensions/e2e/testing"] != "E2E dimension" {
		return fmt.Errorf("dynamic dimension label missing")
	}
	return nil
}
