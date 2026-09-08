package world

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "world.legacy-layout-and-extractors", Suite: "world", Tags: []string{"regression", "mcmap"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: legacyExtraction},
		{ID: "world.map-render-and-cache", Suite: "world", Tags: []string{"regression", "minecraft", "mcmap"}, Recipe: recipes.World, Isolation: engine.Fresh, Timeout: 8 * time.Minute, Run: mapRendering},
		{ID: "world.claims-and-player-locations", Suite: "world", Tags: []string{"regression", "minecraft", "mcmap"}, Recipe: recipes.World, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: extraction},
		{ID: "world.scoped-restore-and-rollback", Suite: "world", Tags: []string{"regression", "minecraft", "restic"}, Recipe: recipes.World, Isolation: engine.Fresh, Timeout: 8 * time.Minute, Run: scopedRestore},
		{ID: "world.preview-lifecycle", Suite: "world", Tags: []string{"regression", "minecraft", "restic"}, Recipe: recipes.World, Isolation: engine.Fresh, Timeout: 5 * time.Minute, Run: previewLifecycle},
		{ID: "world.chunk-prune", Suite: "world", Tags: []string{"regression", "minecraft", "mcmap"}, Recipe: recipes.World, Isolation: engine.Fresh, Timeout: 4 * time.Minute, Run: chunkPrune},
		{ID: "world.interrupted-restore-recovery", Suite: "world", Tags: []string{"regression", "minecraft", "restic"}, Recipe: recipes.World, Isolation: engine.Fresh, Timeout: 4 * time.Minute, Run: interruptedRestore},
		{ID: "world.missing-sidecars-and-rollback", Suite: "world", Tags: []string{"regression", "minecraft", "restic", "mcmap"}, Recipe: recipes.World, Isolation: engine.Fresh, Timeout: 5 * time.Minute, Run: missingSidecars},
		{ID: "world.disconnect-restore-and-maintenance", Suite: "world", Tags: []string{"regression", "minecraft", "restic"}, Recipe: recipes.World, Isolation: engine.Fresh, Timeout: 4 * time.Minute, Run: disconnectedRestore},
	}
}

type scenario struct {
	t        *engine.Scope
	client   *api.Client
	id, base string
}

func open(ctx context.Context, t *engine.Scope) (*scenario, error) {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return nil, err
	}
	id := fixtures.ServerOf(t.Env).ID
	return &scenario{t: t, client: client, id: id, base: "/api/servers/" + id}, nil
}

func (s *scenario) stop(ctx context.Context) error {
	if err := fixtures.Operation(ctx, s.client, s.id, "stop"); err != nil {
		return err
	}
	return fixtures.WaitStatus(ctx, s.client, s.id, "created")
}

func (s *scenario) snapshot(ctx context.Context, selection map[string]any) (string, error) {
	var response struct {
		Snapshot struct {
			ID string `json:"id"`
		} `json:"snapshot"`
	}
	if err := s.client.JSON(ctx, "POST", s.base+"/world-restore/snapshots", selection, &response, 200); err != nil {
		return "", err
	}
	if response.Snapshot.ID == "" {
		return "", fmt.Errorf("world snapshot returned no ID")
	}
	return response.Snapshot.ID, nil
}

func (s *scenario) config(ctx context.Context, module string, mutate func(map[string]any)) error {
	var response struct {
		Data map[string]any `json:"config_data"`
	}
	if err := s.client.JSON(ctx, "GET", "/api/config/modules/"+module, nil, &response, 200); err != nil {
		return err
	}
	mutate(response.Data)
	return s.client.JSON(ctx, "PUT", "/api/config/modules/"+module, map[string]any{"config_data": response.Data}, nil, 200)
}

func request(snapshot string, selection map[string]any) map[string]any {
	return map[string]any{"source_snapshot_id": snapshot, "selection": selection}
}
