package dns

import (
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/evidence"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
)

//go:embed cloud_helper.py
var cleanupScript string

type cloudManifest struct {
	Version     int       `json:"version"`
	Provider    string    `json:"provider"`
	Domain      string    `json:"domain"`
	Scope       string    `json:"scope"`
	Environment string    `json:"environment"`
	RunID       string    `json:"run_id"`
	Created     time.Time `json:"created"`
	Armed       bool      `json:"armed"`
	Cleaned     bool      `json:"cleaned"`
	Helper      string    `json:"helper"`
}

func cloudCommand(ctx context.Context, docker platform.Docker, image, directory, runID, envID, operation string) (output string, err error) {
	name := "mca-dns-helper-" + envID
	defer func() {
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		err = errors.Join(err, docker.RemoveOwned(cleanupCtx, name, runID, envID))
	}()
	return docker.Run(ctx, "run", "--rm", "--name", name,
		"--label", platform.RunLabel+"="+runID, "--label", platform.EnvLabel+"="+envID,
		"--mount", "type=bind,src="+directory+",dst=/recovery,readonly", image,
		"python", "/recovery/dns-cleanup.py", "/recovery/dns-external.json", operation)
}

func prepareCloud(ctx context.Context, t *engine.Scope, provider string) (providerConfig, string, error) {
	options := environment.Get[fixtures.Options](t.Env, "options")
	config, err := loadConfig(options.ExternalConfig, provider)
	if err != nil {
		return config, "", err
	}
	t.Recorder.Redactor.Add(config.ID, config.Key, config.AK, config.SK)
	t.Env.Set("cloud-config", config)
	scope := config.scope(t.Env.ID)
	journal := environment.Get[*platform.Journal](t.Env, "journal")
	manifest := cloudManifest{Version: 1, Provider: provider, Domain: config.Domain, Scope: scope, Environment: t.Env.ID, RunID: journal.Manifest.RunID, Created: time.Now().UTC()}
	manifest.Helper = "mca-dns-helper-" + t.Env.ID
	if err = journal.Track(t.Env.ID, manifest.Helper, ""); err != nil {
		return config, scope, err
	}
	manifestDirectory := filepath.Join(journal.Manifest.Directory, "cloud")
	if err = os.MkdirAll(manifestDirectory, 0700); err != nil {
		return config, scope, err
	}
	manifestPath := filepath.Join(manifestDirectory, t.Env.ID+".json")
	if err = evidence.WriteJSON(manifestPath, manifest); err != nil {
		return config, scope, err
	}
	t.Recorder.Event("external_dns_scope", manifest)
	helperData, err := json.Marshal(map[string]any{"provider": provider, "scope": scope, "config": config})
	if err != nil {
		return config, scope, err
	}
	if err = os.WriteFile(filepath.Join(t.Env.Dir, "dns-external.json"), helperData, 0600); err != nil {
		return config, scope, err
	}
	if err = os.WriteFile(filepath.Join(t.Env.Dir, "dns-cleanup.py"), []byte(cleanupScript), 0600); err != nil {
		return config, scope, err
	}
	manifest.Armed = true
	if err = evidence.WriteJSON(manifestPath, manifest); err != nil {
		return config, scope, err
	}
	t.Cleanup(func(cleanupCtx context.Context) error {
		backend := fixtures.BackendOf(t.Env)
		container, err := backend.Docker.Inspect(cleanupCtx, backend.Name)
		if err != nil {
			return err
		}
		if container != nil && container.State.Running {
			if container.Config.Labels[platform.RunLabel] != manifest.RunID || container.Config.Labels[platform.EnvLabel] != manifest.Environment {
				return fmt.Errorf("backend ownership mismatch before cloud cleanup")
			}
			if _, err = backend.Docker.Run(cleanupCtx, "stop", "--time", "10", container.ID); err != nil {
				return err
			}
		}
		output, err := cloudCommand(cleanupCtx, journal.Docker, options.Image, t.Env.Dir, manifest.RunID, manifest.Environment, "cleanup")
		t.Recorder.Event("external_dns_cleanup", map[string]any{"manifest": manifest, "output": output})
		if err != nil {
			return fmt.Errorf("cloud cleanup failed; recover using %s: %w", manifestPath, err)
		}
		manifest.Cleaned = true
		return evidence.WriteJSON(manifestPath, manifest)
	})
	_, err = cloudCommand(ctx, journal.Docker, options.Image, t.Env.Dir, manifest.RunID, manifest.Environment, "protect")
	return config, scope, err
}

func RecoverCloud(ctx context.Context, docker platform.Docker, image, externalConfig, manifestPath string) error {
	lock, err := platform.TryLock(manifestPath + ".lock")
	if err != nil {
		return err
	}
	defer lock.Close()
	data, err := os.ReadFile(manifestPath)
	if err != nil {
		return err
	}
	var manifest cloudManifest
	if err = json.Unmarshal(data, &manifest); err != nil {
		return err
	}
	config, err := loadConfig(externalConfig, manifest.Provider)
	if err != nil {
		return err
	}
	if !manifest.Armed || manifest.Cleaned {
		return nil
	}
	config.Domain = manifest.Domain
	containers, err := docker.Run(ctx, "ps", "-q", "--filter", "label="+platform.RunLabel+"="+manifest.RunID, "--filter", "label="+platform.EnvLabel+"="+manifest.Environment)
	if err != nil {
		return err
	}
	if containers != "" {
		return fmt.Errorf("stop/reclaim the manifest's local environment before cloud recovery")
	}
	directory, err := os.MkdirTemp("", "mc-admin-dns-recovery-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(directory)
	data, err = json.Marshal(map[string]any{"provider": manifest.Provider, "scope": manifest.Scope, "config": config})
	if err != nil {
		return err
	}
	if err = os.WriteFile(filepath.Join(directory, "dns-external.json"), data, 0600); err != nil {
		return err
	}
	if err = os.WriteFile(filepath.Join(directory, "dns-cleanup.py"), []byte(cleanupScript), 0600); err != nil {
		return err
	}
	_, err = cloudCommand(ctx, docker, image, directory, manifest.RunID, manifest.Environment, "cleanup")
	if err != nil {
		redactor := &evidence.Redactor{}
		redactor.Add(config.ID, config.Key, config.AK, config.SK)
		return errors.New(redactor.Text(err.Error()))
	}
	manifest.Cleaned = true
	return evidence.WriteJSON(manifestPath, manifest)
}
