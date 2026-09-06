package selfcheck

import (
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(r fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "selfcheck.execution-history-and-stream", Suite: "selfcheck", Tags: []string{"regression"}, Recipe: r.Base, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: history},
		{ID: "selfcheck.game-port-current-state", Suite: "selfcheck", Tags: []string{"regression"}, Recipe: r.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: gamePort},
		{ID: "selfcheck.jar-metadata-and-ownership", Suite: "selfcheck", Tags: []string{"regression"}, Recipe: r.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: jarMetadata},
		{ID: "selfcheck.repository-health", Suite: "selfcheck", Tags: []string{"regression", "restic"}, Recipe: r.Backup, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: repositoryHealth},
		{ID: "selfcheck.dependency-and-filesystem-recovery", Suite: "selfcheck", Tags: []string{"regression"}, Recipe: r.Server, Isolation: engine.Fresh, Timeout: 2 * time.Minute, Run: dependencyAndFilesystem},
	}
}
