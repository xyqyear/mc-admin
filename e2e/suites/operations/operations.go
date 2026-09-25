package operations

import (
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "operations.interrupted-task-and-cron-history", Suite: "operations", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: interruptedHistory},
		{ID: "operations.scoped-recovery-and-permissions", Suite: "operations", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 3 * time.Minute, Run: scopedRecovery},
		{ID: "operations.cache-degradation-and-recovery", Suite: "operations", Tags: []string{"regression"}, Recipe: recipes.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: cacheRecovery},
	}
}

type operation struct {
	ID             string     `json:"operation_id"`
	Kind           string     `json:"kind"`
	Origin         string     `json:"origin"`
	LegacyID       string     `json:"legacy_id"`
	State          string     `json:"state"`
	Phase          string     `json:"phase"`
	Created        time.Time  `json:"created_at"`
	Ended          *time.Time `json:"ended_at"`
	Changed        bool       `json:"data_changed"`
	WritersStopped bool       `json:"writers_stopped"`
	Reason         *string    `json:"recovery_reason"`
	CacheDegraded  bool       `json:"cache_degraded"`
	ResolvedBy     *int       `json:"resolved_by"`
	ResolvedAt     *time.Time `json:"resolved_at"`
	Resources      []struct {
		Kind       string `json:"kind"`
		ServerID   string `json:"server_id"`
		Generation int    `json:"generation"`
	} `json:"resources"`
}
