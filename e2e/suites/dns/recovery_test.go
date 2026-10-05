package dns

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"mc-admin/e2e/internal/evidence"
	"mc-admin/e2e/internal/platform"
)

func TestRecoveryUsesRecordedCloudTargetAfterConfigurationChanges(t *testing.T) {
	directory := t.TempDir()
	config := providerConfig{Domain: "current.example.com", ManagedSubDomain: "current-parent", AK: "fresh-ak", SK: "fresh-sk"}
	manifest := cloudManifest{Version: 1, Provider: "huawei", Domain: "original.example.com", Scope: "legacy-name.original-parent", Environment: "012345abcdef", RunID: "e2e-12345678", Armed: true, Helper: "mca-dns-helper-012345abcdef"}
	manifestPath := filepath.Join(directory, "manifest.json")
	configPath := filepath.Join(directory, "external.json")
	for path, value := range map[string]any{manifestPath: manifest, configPath: map[string]any{"dns": map[string]any{"huawei": config}}} {
		if err := evidence.WriteJSON(path, value); err != nil {
			t.Fatal(err)
		}
	}
	targetPath := filepath.Join(directory, "recovery-target.json")
	script := `#!/bin/sh
case "$3" in
  ps) ;;
  run)
    for argument in "$@"; do
      case "$argument" in
        type=bind,src=*,dst=/recovery,readonly)
          directory=${argument#type=bind,src=}
          directory=${directory%,dst=/recovery,readonly}
          cp "$directory/dns-external.json" "$E2E_RECOVERY_TARGET" ;;
      esac
    done ;;
  container) echo 'No such container' >&2; exit 1 ;;
  *) exit 2 ;;
esac
`
	if err := os.WriteFile(filepath.Join(directory, "docker"), []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", directory+":"+os.Getenv("PATH"))
	t.Setenv("E2E_RECOVERY_TARGET", targetPath)
	if err := RecoverCloud(context.Background(), platform.Docker{Socket: "/unused.sock"}, "test-image", configPath, manifestPath); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(targetPath)
	if err != nil {
		t.Fatal(err)
	}
	var target struct {
		Provider string
		Scope    string
		Config   providerConfig
	}
	if err = json.Unmarshal(data, &target); err != nil {
		t.Fatal(err)
	}
	if target.Provider != manifest.Provider || target.Scope != manifest.Scope || target.Config.Domain != manifest.Domain || target.Config.AK != config.AK || target.Config.SK != config.SK {
		t.Fatalf("recovery did not target recorded records with fresh credentials: %+v", target)
	}
}

func TestRecoveryAfterRuntimeLoss(t *testing.T) {
	for _, state := range []string{"success", "failure", "running", "locked"} {
		t.Run(state, func(t *testing.T) {
			directory := t.TempDir()
			config := providerConfig{Domain: "example.com", ManagedSubDomain: "e2e-test-mc", Region: "cn-north-4", AK: "private-ak", SK: "private-sk", TTL: 600}
			manifest := cloudManifest{Version: 1, Provider: "huawei", Domain: config.Domain, Scope: config.scope("012345abcdef"), Environment: "012345abcdef", RunID: "e2e-12345678", Armed: true, Helper: "mca-dns-helper-012345abcdef"}
			manifestPath := filepath.Join(directory, "manifest.json")
			configPath := filepath.Join(directory, "external.json")
			for path, value := range map[string]any{manifestPath: manifest, configPath: map[string]any{"dns": map[string]any{"huawei": config}}} {
				if err := evidence.WriteJSON(path, value); err != nil {
					t.Fatal(err)
				}
			}
			marker := filepath.Join(directory, "cloud-mutations")
			script := `#!/bin/sh
case "$3" in
  ps) if [ "$E2E_RECOVERY_STATE" = running ]; then echo owned-backend; fi ;;
  run)
    echo cleanup >> "$E2E_RECOVERY_MARKER"
    if [ "$E2E_RECOVERY_STATE" = failure ]; then echo private-sk >&2; exit 1; fi ;;
  container) echo 'No such container' >&2; exit 1 ;;
  *) exit 2 ;;
esac
`
			if err := os.WriteFile(filepath.Join(directory, "docker"), []byte(script), 0700); err != nil {
				t.Fatal(err)
			}
			t.Setenv("PATH", directory+":"+os.Getenv("PATH"))
			t.Setenv("E2E_RECOVERY_STATE", state)
			t.Setenv("E2E_RECOVERY_MARKER", marker)
			if state == "locked" {
				lock, err := platform.TryLock(manifestPath + ".lock")
				if err != nil {
					t.Fatal(err)
				}
				defer lock.Close()
			}
			recover := func() error {
				return RecoverCloud(context.Background(), platform.Docker{Socket: "/unused.sock"}, "test-image", configPath, manifestPath)
			}
			err := recover()
			if (err == nil) != (state == "success") {
				t.Fatalf("state=%s error=%v", state, err)
			}
			if err != nil && strings.Contains(err.Error(), "private-sk") {
				t.Fatal("recovery exposed credentials")
			}
			data, err := os.ReadFile(manifestPath)
			if err != nil {
				t.Fatal(err)
			}
			if err := json.Unmarshal(data, &manifest); err != nil || manifest.Cleaned != (state == "success") {
				t.Fatalf("unexpected cleanup receipt: %+v, %v", manifest, err)
			}
			if state == "success" {
				if err := recover(); err != nil {
					t.Fatal(err)
				}
			}
			data, err = os.ReadFile(marker)
			if state == "running" || state == "locked" {
				if !os.IsNotExist(err) {
					t.Fatal("unsafe recovery reached cloud mutation")
				}
			} else if err != nil || string(data) != "cleanup\n" {
				t.Fatalf("unexpected recovery mutations: %q, %v", data, err)
			}
			if state == "running" {
				t.Setenv("E2E_RECOVERY_STATE", "success")
				if err := recover(); err != nil {
					t.Fatalf("recovery failed after the local writer stopped: %v", err)
				}
				data, err := os.ReadFile(marker)
				if err != nil || string(data) != "cleanup\n" {
					t.Fatalf("recorded cloud resources were not cleaned after writer termination: %q, %v", data, err)
				}
			}
		})
	}
}
