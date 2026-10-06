package world

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
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

func TestClaimsAliasOracleComparesCompleteClustersByStableIdentity(t *testing.T) {
	const claims = `{"available":true,"detected_format":"snbt","teams":[{"id":"team","display_name":"Builders","total_chunks":4,"clusters":[{"id":"team#world/region#0","region_dir_relpath":"world/region","chunks":[[0,0],[1,0]],"force_loaded":[[0,0]],"centroid_block":[16,8]},{"id":"team#_#0","region_dir_relpath":null,"chunks":[[-1,-1]],"force_loaded":[],"centroid_block":[-8,-8]},{"id":"team#world/region#1","region_dir_relpath":"world/region","chunks":[[10,10]],"force_loaded":[],"centroid_block":[168,168]}]}]}`
	for _, test := range []struct {
		name       string
		mutate     func(*claimsResponse)
		shouldFail bool
	}{
		{"same payload", func(*claimsResponse) {}, false},
		{"reordered dimensions", func(response *claimsResponse) {
			clusters := response.Teams[0].Clusters
			clusters[0], clusters[1], clusters[2] = clusters[2], clusters[0], clusters[1]
		}, false},
		{"changed chunks", func(response *claimsResponse) { response.Teams[0].Clusters[0].Chunks[0][0] = 99 }, true},
		{"changed forced chunks", func(response *claimsResponse) { response.Teams[0].Clusters[0].Forced[0][0] = 99 }, true},
		{"changed centroid", func(response *claimsResponse) { response.Teams[0].Clusters[0].Centroid[0] = 99 }, true},
		{"changed dimension", func(response *claimsResponse) {
			region := "world/other/region"
			response.Teams[0].Clusters[0].Region = &region
		}, true},
		{"changed total", func(response *claimsResponse) { response.Teams[0].Total++ }, true},
		{"duplicate identity", func(response *claimsResponse) { response.Teams[0].Clusters[2].ID = response.Teams[0].Clusters[0].ID }, true},
		{"empty identity", func(response *claimsResponse) { response.Teams[0].Clusters[0].ID = "" }, true},
		{"missing cluster", func(response *claimsResponse) { response.Teams[0].Clusters = response.Teams[0].Clusters[:2] }, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			var actual, baseline, before claimsResponse
			for _, response := range []*claimsResponse{&actual, &baseline, &before} {
				if err := json.Unmarshal([]byte(claims), response); err != nil {
					t.Fatal(err)
				}
			}
			test.mutate(&actual)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/api/servers/owned/claims" {
					t.Errorf("unexpected alias path %s", r.URL.Path)
				}
				if err := json.NewEncoder(w).Encode(actual); err != nil {
					t.Errorf("encode alias response: %v", err)
				}
			}))
			defer server.Close()
			client := api.New(server.URL, nil)
			defer client.Close()
			err := claimsAliasMatches(context.Background(), client, "/api/servers/owned", baseline)
			if (err != nil) != test.shouldFail {
				t.Fatalf("alias comparison error = %v, should fail = %v", err, test.shouldFail)
			}
			if !reflect.DeepEqual(baseline, before) {
				t.Fatal("comparison modified the baseline response or its shared slices")
			}
		})
	}
}
