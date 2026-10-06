package world

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"mc-admin/e2e/internal/api"
)

func TestWorldAliasOracleRejectsSameLengthChanges(t *testing.T) {
	const claims = `{"available":true,"detected_format":"snbt","teams":[{"id":"team","display_name":"Builders","total_chunks":1,"clusters":[{"id":"cluster","region_dir_relpath":"world/region","chunks":[[1,2]],"force_loaded":[],"centroid_block":[24,40]}]}]}`
	const locations = `{"players":[{"uuid":"player","dimension_id":"minecraft:overworld","region_dir_relpath":"world/region","pos":{"X":24.5,"Y":65,"Z":-8.25}}],"skipped":[{"reason":"parse_error"}]}`
	for _, test := range []struct {
		name, path, body string
		shouldFail       bool
	}{
		{"same claims", "/claims", claims, false},
		{"changed team", "/claims", `{"available":true,"detected_format":"snbt","teams":[{"id":"other","display_name":"Builders","total_chunks":1,"clusters":[{"id":"cluster","region_dir_relpath":"world/region","chunks":[[1,2]],"force_loaded":[],"centroid_block":[24,40]}]}]}`, true},
		{"changed cluster", "/claims", `{"available":true,"detected_format":"snbt","teams":[{"id":"team","display_name":"Builders","total_chunks":1,"clusters":[{"id":"other","region_dir_relpath":"world/region","chunks":[[1,2]],"force_loaded":[],"centroid_block":[24,40]}]}]}`, true},
		{"same locations", "/player-locations", locations, false},
		{"changed position", "/player-locations", `{"players":[{"uuid":"player","dimension_id":"minecraft:overworld","region_dir_relpath":"world/region","pos":{"X":99,"Y":65,"Z":-8.25}}],"skipped":[{"reason":"parse_error"}]}`, true},
		{"changed identity", "/player-locations", `{"players":[{"uuid":"other","dimension_id":"minecraft:overworld","region_dir_relpath":"world/region","pos":{"X":24.5,"Y":65,"Z":-8.25}}],"skipped":[{"reason":"parse_error"}]}`, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/api/servers/owned"+test.path {
					t.Errorf("unexpected alias path %s", r.URL.Path)
				}
				_, _ = w.Write([]byte(test.body))
			}))
			defer server.Close()
			client := api.New(server.URL, nil)
			defer client.Close()
			var err error
			if test.path == "/claims" {
				var baseline claimsResponse
				if err := json.Unmarshal([]byte(claims), &baseline); err != nil {
					t.Fatal(err)
				}
				err = claimsAliasMatches(context.Background(), client, "/api/servers/owned", baseline)
				if baseline.Teams[0].ID != "team" || baseline.Teams[0].Clusters[0].ID != "cluster" {
					t.Fatal("claims baseline was modified")
				}
			} else {
				var baseline playerLocationsResponse
				if err := json.Unmarshal([]byte(locations), &baseline); err != nil {
					t.Fatal(err)
				}
				err = playerLocationsAliasMatches(context.Background(), client, "/api/servers/owned", baseline)
				if baseline.Players[0].UUID != "player" || baseline.Players[0].Pos.X != 24.5 {
					t.Fatal("player baseline was modified")
				}
			}
			if (err != nil) != test.shouldFail {
				t.Fatalf("alias comparison error = %v, should fail = %v", err, test.shouldFail)
			}
		})
	}
}
