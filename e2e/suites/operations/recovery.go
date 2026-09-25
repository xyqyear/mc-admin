package operations

import (
	"context"
	"crypto/sha256"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func scopedRecovery(ctx context.Context, t *engine.Scope) error {
	owner, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	admin, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	anonymous, err := fixtures.Session(ctx, t, "")
	if err != nil {
		return err
	}
	var me struct {
		ID int `json:"id"`
	}
	if err = owner.JSON(ctx, "GET", "/api/user/me", nil, &me, 200); err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	id, operationID := server.ID, "e2e-interrupted-configuration"
	independent, err := createIndependentServer(ctx, t, owner)
	if err != nil {
		return err
	}
	if err = fixtures.CreateFile(ctx, owner, id, "/recovery-marker.txt", "blocked data stays intact"); err != nil {
		return err
	}
	if err = prepareInterruptedHistory(ctx, t, []interruptedInput{{
		ID: operationID, Kind: "server_rebuild", Origin: "task", ServerID: id,
		Resource: "configuration", ConfigurationVersion: fmt.Sprintf("%x", sha256.Sum256([]byte(server.Compose))), Changed: true,
	}}); err != nil {
		return err
	}
	if err = replaceOwnedCompose(t, server.Compose+"\n# E2E configuration changed before interruption\n"); err != nil {
		return err
	}
	if err = fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
		return err
	}
	path := "/api/operations/" + operationID
	resolve := map[string]any{"action": "configuration_reconciled"}
	checkBlocked := func() error {
		result, err := loadOperation(ctx, owner, operationID)
		if err != nil {
			return err
		}
		if err = interrupted(result, operationID, id); err != nil {
			return err
		}
		if result.Reason == nil || !strings.Contains(*result.Reason, "配置") || result.ResolvedBy != nil || result.ResolvedAt != nil {
			return fmt.Errorf("configuration mismatch lost its unresolved recovery block: %+v", result)
		}
		if err = owner.JSON(ctx, "POST", "/api/servers/"+id+"/files/content?path=/recovery-marker.txt", map[string]string{"content": "rejected write"}, nil, 423); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, owner, id, "/recovery-marker.txt", "blocked data stays intact")
	}
	if err = t.Step("configuration uncertainty blocks one server while another remains writable", func() error {
		if err := checkBlocked(); err != nil {
			return err
		}
		if err := fixtures.CreateFile(ctx, owner, independent, "/independent.txt", "unrelated server remains writable"); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, owner, independent, "/independent.txt", "unrelated server remains writable")
	}); err != nil {
		return err
	}
	if err = t.Step("history enforces login and owner plus CSRF for recovery; rejections preserve the block", func() error {
		for _, route := range []string{"/api/operations", path} {
			if err := anonymous.JSON(ctx, "GET", route, nil, nil, 401); err != nil {
				return err
			}
			if err := admin.JSON(ctx, "GET", route, nil, nil, 200); err != nil {
				return err
			}
		}
		if err := anonymous.JSON(ctx, "POST", path+"/resolve", resolve, nil, 401); err != nil {
			return err
		}
		if err := admin.JSON(ctx, "POST", path+"/resolve", resolve, nil, 403); err != nil {
			return err
		}
		owner.CSRF = false
		csrfError := owner.JSON(ctx, "POST", path+"/resolve", resolve, nil, 403)
		owner.CSRF = true
		if csrfError != nil {
			return csrfError
		}
		if err := owner.JSON(ctx, "POST", path+"/resolve", map[string]any{"action": "configuration_reconciled", "force": true}, nil, 422); err != nil {
			return err
		}
		if err := owner.JSON(ctx, "POST", path+"/resolve", resolve, nil, 409); err != nil {
			return err
		}
		if err := owner.JSON(ctx, "POST", path+"/resolve", map[string]string{"action": "acknowledge_partial"}, nil, 409); err != nil {
			return err
		}
		if err := owner.JSON(ctx, "GET", "/api/operations/e2e-missing", nil, nil, 404); err != nil {
			return err
		}
		if err := owner.JSON(ctx, "GET", "/api/operations?limit=0", nil, nil, 422); err != nil {
			return err
		}
		var public map[string]any
		if err := owner.JSON(ctx, "GET", path, nil, &public, 200); err != nil {
			return err
		}
		for _, internal := range []string{"processes", "processes_json", "ownership_known", "configuration_version", "resources_json"} {
			if _, exists := public[internal]; exists {
				return fmt.Errorf("operation API exposed internal recovery field %s", internal)
			}
		}
		return checkBlocked()
	}); err != nil {
		return err
	}
	if err = t.Step("repairing the owned Compose allows an explicit recorded recovery decision", func() error {
		if err := replaceOwnedCompose(t, server.Compose); err != nil {
			return err
		}
		var result operation
		if err := owner.JSON(ctx, "POST", path+"/resolve", resolve, &result, 200); err != nil {
			return err
		}
		if result.State != "interrupted" || result.Reason != nil || result.ResolvedBy == nil || *result.ResolvedBy != me.ID || result.ResolvedAt == nil {
			return fmt.Errorf("successful recovery lost its actor or rewrote the interrupted outcome: %+v", result)
		}
		if err := fixtures.WriteFile(ctx, owner, id, "/recovery-marker.txt", "explicit recovery permitted this write"); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, owner, id, "/recovery-marker.txt", "explicit recovery permitted this write")
	}); err != nil {
		return err
	}
	return t.Step("recovery evidence and unblocked writes survive another restart", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		result, err := loadOperation(ctx, owner, operationID)
		if err != nil {
			return err
		}
		if result.Reason != nil || result.ResolvedBy == nil || *result.ResolvedBy != me.ID || result.State != "interrupted" {
			return fmt.Errorf("recovery decision did not persist: %+v", result)
		}
		if err := fixtures.CheckFile(ctx, owner, id, "/recovery-marker.txt", "explicit recovery permitted this write"); err != nil {
			return err
		}
		return fixtures.WriteFile(ctx, owner, id, "/recovery-marker.txt", "writable after restart")
	})
}

func cacheRecovery(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id, operationID := fixtures.ServerOf(t.Env).ID, "e2e-interrupted-cache"
	if err = fixtures.CreateFile(ctx, client, id, "/world-marker.txt", "world data is authoritative"); err != nil {
		return err
	}
	if err = fixtures.CreateFile(ctx, client, id, "/.mcmap/tiles", "not a directory; cache cleanup must degrade"); err != nil {
		return err
	}
	if err = prepareInterruptedHistory(ctx, t, []interruptedInput{{
		ID: operationID, Kind: "chunk_prune_preview", Origin: "task", ServerID: id, Resource: "cache", Changed: true,
	}}); err != nil {
		return err
	}
	if err = fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
		return err
	}
	if err = t.Step("cache cleanup failure is observable while normal files and new tasks remain available", func() error {
		result, err := loadOperation(ctx, client, operationID)
		if err != nil {
			return err
		}
		if err = interrupted(result, operationID, id); err != nil {
			return err
		}
		if !result.CacheDegraded || result.Reason != nil {
			return fmt.Errorf("cache-only failure did not remain a nonblocking degradation: %+v", result)
		}
		if err := fixtures.CheckFile(ctx, client, id, "/world-marker.txt", "world data is authoritative"); err != nil {
			return err
		}
		if err := fixtures.CreateFile(ctx, client, id, "/management.txt", "cache failure did not freeze management"); err != nil {
			return err
		}
		var task struct {
			ID string `json:"task_id"`
		}
		if err := client.JSON(ctx, "POST", "/api/servers/"+id+"/files/ownership/restore", nil, &task, 200); err != nil {
			return err
		}
		if _, err := client.Task(ctx, task.ID); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/management.txt", "cache failure did not freeze management")
	}); err != nil {
		return err
	}
	if err = client.JSON(ctx, "DELETE", "/api/servers/"+id+"/files?path=/.mcmap/tiles", nil, nil, 200); err != nil {
		return err
	}
	if err = fixtures.CreateFile(ctx, client, id, "/.mcmap/tiles/stale-cache.txt", "cache can be discarded"); err != nil {
		return err
	}
	return t.Step("a later restart clears the repaired cache and its degradation without changing world data", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		result, err := loadOperation(ctx, client, operationID)
		if err != nil {
			return err
		}
		if result.State != "interrupted" || result.CacheDegraded || result.Reason != nil {
			return fmt.Errorf("cache remained degraded after successful invalidation: %+v", result)
		}
		if err := client.JSON(ctx, "GET", "/api/servers/"+id+"/files/content?path=/.mcmap/tiles/stale-cache.txt", nil, nil, 404); err != nil {
			return err
		}
		if err := fixtures.CheckFile(ctx, client, id, "/world-marker.txt", "world data is authoritative"); err != nil {
			return err
		}
		return fixtures.WriteFile(ctx, client, id, "/management.txt", "management still works after cache recovery")
	})
}
