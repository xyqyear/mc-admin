package minecraft

import (
	"context"
	"fmt"
	"sync"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func sharedMonitoring(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	first, err := fixtures.WaitServerMetrics(ctx, client, id)
	if err != nil {
		return err
	}
	if first.Generation <= 0 || first.Incarnation == nil {
		return fmt.Errorf("runtime samples have no instance identity")
	}
	if err = t.Step("concurrent observers read the same registered instance", func() error {
		var workers sync.WaitGroup
		results := make(chan error, 10)
		for range 10 {
			workers.Go(func() {
				observed, readErr := fixtures.ServerMonitoring(ctx, client, id)
				if readErr == nil && (observed.Generation != first.Generation || observed.Incarnation == nil || *observed.Incarnation != *first.Incarnation || observed.CPU.SampledAt == nil) {
					readErr = fmt.Errorf("observation lost its instance or sample identity")
				}
				results <- readErr
			})
		}
		workers.Wait()
		close(results)
		for result := range results {
			if result != nil {
				return result
			}
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("stop removes running metrics and restart resets the container sampling identity", func() error {
		if err := fixtures.Operation(ctx, client, id, "stop"); err != nil {
			return err
		}
		if err := fixtures.WaitStatus(ctx, client, id, "created"); err != nil {
			return err
		}
		stopped, err := fixtures.ServerMonitoring(ctx, client, id)
		if err != nil {
			return err
		}
		if stopped.CPU.Value != nil || stopped.Memory.Value != nil || stopped.CPU.Quality != "unavailable" || stopped.Maintenance.Active {
			return fmt.Errorf("stopped server retained running metrics or maintenance")
		}
		if err := fixtures.Operation(ctx, client, id, "start"); err != nil {
			return err
		}
		if err := fixtures.WaitStatus(ctx, client, id, "healthy"); err != nil {
			return err
		}
		restarted, err := fixtures.WaitServerMetrics(ctx, client, id)
		if err != nil {
			return err
		}
		if restarted.Generation != first.Generation || restarted.Incarnation == nil || *restarted.Incarnation == *first.Incarnation {
			return fmt.Errorf("restart did not reset its sampling incarnation")
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("startup intent uses live container state after removal", func() error {
		if err := fixtures.Operation(ctx, client, id, "stop"); err != nil {
			return err
		}
		if err := fixtures.WaitStatus(ctx, client, id, "created"); err != nil {
			return err
		}
		if err := fixtures.Operation(ctx, client, id, "down"); err != nil {
			return err
		}
		if err := fixtures.Operation(ctx, client, id, "start"); err != nil {
			return err
		}
		if err := fixtures.WaitStatus(ctx, client, id, "healthy"); err != nil {
			return err
		}
		return client.JSON(ctx, "POST", "/api/servers/"+id+"/rcon", map[string]string{"command": "list"}, nil, 200)
	})
}
