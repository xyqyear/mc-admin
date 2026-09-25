package servers

import (
	"context"
	"fmt"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type scheduleIdentity struct {
	ID         string  `json:"cronjob_id"`
	Name       string  `json:"name"`
	Status     string  `json:"status"`
	Cron       string  `json:"cron"`
	Generation *int    `json:"managed_server_generation"`
	Purpose    *string `json:"managed_purpose"`
	Issue      *string `json:"managed_binding_issue"`
}

func readScheduleIdentity(ctx context.Context, c *api.Client, id string) (scheduleIdentity, error) {
	var result scheduleIdentity
	err := c.JSON(ctx, "GET", "/api/cron/"+id, nil, &result, 200)
	return result, err
}

func scheduleGeneration(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	base := "/api/servers/" + server.ID
	var independent, managed scheduleIdentity
	if err = c.JSON(ctx, "POST", "/api/cron/", map[string]any{
		"identifier": "restart_server", "params": map[string]string{"server_id": server.ID},
		"name": "restart-" + server.ID, "cron": "0 8 1 1 *",
	}, &independent, 200); err != nil {
		return err
	}
	if err = c.JSON(ctx, "POST", base+"/restart-schedule", map[string]string{"custom_cron": "0 6 1 1 *"}, &managed, 200); err != nil {
		return err
	}
	first, err := readScheduleIdentity(ctx, c, managed.ID)
	if err != nil {
		return err
	}
	if first.ID == independent.ID || first.Generation == nil || *first.Generation <= 0 || first.Purpose == nil || *first.Purpose != "restart" || first.Issue != nil {
		return fmt.Errorf("managed schedule did not receive an explicit incarnation binding: %+v", first)
	}
	checkIndependent := func(status string) error {
		actual, err := readScheduleIdentity(ctx, c, independent.ID)
		if err == nil && (actual.Status != status || actual.Cron != "0 8 1 1 *" || actual.Name != "restart-"+server.ID || actual.Generation != nil || actual.Purpose != nil || actual.Issue != nil) {
			return fmt.Errorf("independent job was rebound or altered through its display name: %+v", actual)
		}
		return err
	}
	if err = t.Step("managed mutations and restart preserve an independent job with the same display name", func() error {
		for _, action := range []string{"pause", "resume"} {
			if err := c.JSON(ctx, "POST", base+"/restart-schedule/"+action, nil, nil, 200); err != nil {
				return err
			}
			if err := checkIndependent("active"); err != nil {
				return err
			}
		}
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		return checkIndependent("active")
	}); err != nil {
		return err
	}
	return t.Step("same-name recreation receives a new plan and cannot resume the previous generation", func() error {
		if err := fixtures.Operation(ctx, c, server.ID, "remove"); err != nil {
			return err
		}
		if err := checkIndependent("cancelled"); err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", base, map[string]string{"yaml_content": server.Compose}, nil, 200); err != nil {
			return err
		}
		var absent *scheduleIdentity
		if err := c.JSON(ctx, "GET", base+"/restart-schedule", nil, &absent, 200); err != nil {
			return err
		}
		if absent != nil {
			return fmt.Errorf("new server inherited a previous generation's schedule: %+v", absent)
		}
		if err := c.JSON(ctx, "POST", "/api/cron/"+first.ID+"/resume", nil, nil, 409); err != nil {
			return err
		}
		var replacement scheduleIdentity
		if err := c.JSON(ctx, "POST", base+"/restart-schedule", map[string]string{"custom_cron": "0 7 1 1 *"}, &replacement, 200); err != nil {
			return err
		}
		current, err := readScheduleIdentity(ctx, c, replacement.ID)
		if err != nil {
			return err
		}
		if current.ID == first.ID || current.ID == independent.ID || current.Generation == nil || *current.Generation <= *first.Generation {
			return fmt.Errorf("replacement plan reused a retired identity: %+v", current)
		}
		old, err := readScheduleIdentity(ctx, c, first.ID)
		if err != nil {
			return err
		}
		if old.Status != "cancelled" || old.Generation == nil || *old.Generation != *first.Generation || old.Cron != first.Cron {
			return fmt.Errorf("retired managed schedule history was overwritten: %+v", old)
		}
		if err := checkIndependent("cancelled"); err != nil {
			return err
		}
		if err := c.JSON(ctx, "POST", "/api/cron/"+independent.ID+"/resume", nil, nil, 200); err != nil {
			return err
		}
		if err := checkIndependent("active"); err != nil {
			return err
		}
		return fixtures.Status(ctx, c, server.ID, "exists")
	})
}
