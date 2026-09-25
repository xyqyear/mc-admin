package servers

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type composeVersion struct {
	YAML    string `json:"yaml_content"`
	Version string `json:"version"`
}

type submittedConfiguration struct {
	ID      string `json:"task_id"`
	Skipped bool   `json:"skipped_rebuild"`
}

func readCompose(ctx context.Context, c *api.Client, base string) (composeVersion, error) {
	var result composeVersion
	err := c.JSON(ctx, "GET", base+"/compose", nil, &result, 200)
	if err == nil && (result.Version == "" || result.YAML == "") {
		err = fmt.Errorf("compose lacks content or version")
	}
	return result, err
}

func configurationConflict(ctx context.Context, c *api.Client, method, path string, body any, current string) error {
	var result struct {
		Detail struct {
			Code    string `json:"code"`
			Message string `json:"message"`
			Current string `json:"current_version"`
		} `json:"detail"`
	}
	if err := c.JSON(ctx, method, path, body, &result, 409); err != nil {
		return err
	}
	if result.Detail.Code != "configuration_conflict" || result.Detail.Message == "" || result.Detail.Current != current {
		return fmt.Errorf("configuration conflict lacks safe reconciliation metadata: %+v", result.Detail)
	}
	return nil
}

func stoppedConfigurationTask(ctx context.Context, c *api.Client, id, taskID string) error {
	if taskID == "" {
		return fmt.Errorf("configuration apply did not return a task ID")
	}
	task, err := c.Task(ctx, taskID)
	if err != nil {
		return err
	}
	if wasRunning, ok := task.Result["was_running"].(bool); !ok || wasRunning {
		return fmt.Errorf("configuration task lost its stopped running intent: %+v", task.Result)
	}
	return fixtures.Status(ctx, c, id, "exists")
}

func configurationVersions(ctx context.Context, t *engine.Scope) error {
	owner, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	other, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	base := "/api/servers/" + server.ID
	initial, err := readCompose(ctx, owner, base)
	if err != nil {
		return err
	}
	observed, err := readCompose(ctx, other, base)
	if err != nil {
		return err
	}
	if observed != initial {
		return fmt.Errorf("independent editors did not observe the same baseline")
	}
	var current composeVersion
	if err = t.Step("a stale editor receives a structured conflict without overwriting the accepted content", func() error {
		var accepted submittedConfiguration
		changed := initial.YAML + "\n# accepted by the first editor\n"
		if err := owner.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": changed, "expected_version": initial.Version}, &accepted, 200); err != nil {
			return err
		}
		if err := stoppedConfigurationTask(ctx, owner, server.ID, accepted.ID); err != nil {
			return err
		}
		var err error
		current, err = readCompose(ctx, owner, base)
		if err != nil {
			return err
		}
		if current.YAML != changed || current.Version == initial.Version {
			return fmt.Errorf("accepted compose did not publish a new matching version")
		}
		if err := configurationConflict(ctx, other, "POST", base+"/compose", map[string]string{"yaml_content": initial.YAML, "expected_version": observed.Version}, current.Version); err != nil {
			return err
		}
		preserved, err := readCompose(ctx, other, base)
		if err == nil && preserved != current {
			return fmt.Errorf("rejected editor overwrote the accepted configuration")
		}
		return err
	}); err != nil {
		return err
	}
	if err = t.Step("external Compose edits invalidate an observed version while old clients can still save", func() error {
		project := filepath.Join(t.Env.Dir, "servers", server.ID)
		content := current.YAML + "\n# outside the application\n"
		temporary := filepath.Join(project, "e2e-external-compose.tmp")
		if err := os.WriteFile(temporary, []byte(content), 0600); err != nil {
			return err
		}
		if err := os.Rename(temporary, filepath.Join(project, "docker-compose.yml")); err != nil {
			return err
		}
		external, err := readCompose(ctx, owner, base)
		if err != nil {
			return err
		}
		if external.YAML != content || external.Version == current.Version {
			return fmt.Errorf("external compose edit was invisible to version-aware reads")
		}
		if err := configurationConflict(ctx, owner, "POST", base+"/compose", map[string]string{"yaml_content": initial.YAML, "expected_version": current.Version}, external.Version); err != nil {
			return err
		}
		var accepted submittedConfiguration
		if err := owner.JSON(ctx, "POST", base+"/compose", map[string]string{"yaml_content": server.Compose}, &accepted, 200); err != nil {
			return err
		}
		return stoppedConfigurationTask(ctx, owner, server.ID, accepted.ID)
	}); err != nil {
		return err
	}
	definition := fixtures.TemplateDefinition(t.Env)
	definition["yaml_template"] = strings.Replace(definition["yaml_template"].(string), "MAX_MEMORY: 1G", "MAX_MEMORY: {memory}", 1)
	definition["variable_definitions"] = append(definition["variable_definitions"].([]map[string]any), map[string]any{
		"type": "string", "name": "memory", "display_name": "Memory", "default": "1G",
	})
	var template struct {
		ID int `json:"id"`
	}
	if err = owner.JSON(ctx, "POST", "/api/templates/", definition, &template, 201); err != nil {
		return err
	}
	values := map[string]any{"name": server.ID, "game_port": server.GamePort, "rcon_port": server.RCONPort, "memory": "1G"}
	staleVersion := current.Version
	current, err = readCompose(ctx, owner, base)
	if err != nil {
		return err
	}
	return t.Step("conversion reads share the version and template writes reject stale mode or variables", func() error {
		for _, suffix := range []string{"extract-variables", "check-conversion"} {
			var preview struct {
				Version string `json:"version"`
			}
			if err := owner.JSON(ctx, "POST", base+"/"+suffix, map[string]any{"template_id": template.ID, "variable_values": values}, &preview, 200); err != nil {
				return err
			}
			if preview.Version != current.Version {
				return fmt.Errorf("%s did not preserve the inspected compose version", suffix)
			}
		}
		if err := configurationConflict(ctx, other, "POST", base+"/convert-to-template", map[string]any{"template_id": template.ID, "variable_values": values, "expected_version": staleVersion}, current.Version); err != nil {
			return err
		}
		var converted submittedConfiguration
		if err := owner.JSON(ctx, "POST", base+"/convert-to-template", map[string]any{"template_id": template.ID, "variable_values": values, "expected_version": current.Version}, &converted, 200); err != nil {
			return err
		}
		if !converted.Skipped || converted.ID != "" {
			return fmt.Errorf("identical versioned conversion unnecessarily rebuilt the stopped server")
		}
		var templateConfig struct {
			Version string         `json:"version"`
			Values  map[string]any `json:"variable_values"`
		}
		if err := owner.JSON(ctx, "GET", base+"/template-config", nil, &templateConfig, 200); err != nil {
			return err
		}
		convertedCompose, err := readCompose(ctx, owner, base)
		if err != nil {
			return err
		}
		if templateConfig.Version == "" || templateConfig.Version != convertedCompose.Version || templateConfig.Version == current.Version {
			return fmt.Errorf("mode conversion did not version its source metadata")
		}
		if err := configurationConflict(ctx, other, "PUT", base+"/template-config", map[string]any{"variable_values": values, "expected_version": current.Version}, templateConfig.Version); err != nil {
			return err
		}
		if err := configurationConflict(ctx, other, "POST", base+"/convert-to-direct", map[string]string{"expected_version": current.Version}, templateConfig.Version); err != nil {
			return err
		}
		values["memory"] = "896M"
		var accepted submittedConfiguration
		if err := owner.JSON(ctx, "PUT", base+"/template-config", map[string]any{"variable_values": values, "expected_version": templateConfig.Version}, &accepted, 200); err != nil {
			return err
		}
		if err := stoppedConfigurationTask(ctx, owner, server.ID, accepted.ID); err != nil {
			return err
		}
		latest, err := readCompose(ctx, owner, base)
		if err != nil {
			return err
		}
		if !strings.Contains(latest.YAML, "896M") || latest.Version == templateConfig.Version {
			return fmt.Errorf("template apply did not expose updated content and version")
		}
		if err := owner.JSON(ctx, "POST", base+"/convert-to-direct", map[string]string{"expected_version": latest.Version}, nil, 200); err != nil {
			return err
		}
		direct, err := readCompose(ctx, owner, base)
		if err != nil {
			return err
		}
		if direct.YAML != latest.YAML || direct.Version == latest.Version {
			return fmt.Errorf("direct conversion changed content or failed to version its mode")
		}
		return fixtures.Status(ctx, owner, server.ID, "exists")
	})
}
