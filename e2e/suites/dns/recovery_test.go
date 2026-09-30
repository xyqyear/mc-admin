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

func TestRecoveryRequiresExactAuthorizedIdentity(t *testing.T) {
	config := providerConfig{Domain: "example.com", Prefix: "run", ManagedSubDomain: "e2e-test-mc"}
	manifest := cloudManifest{Version: 1, Provider: "huawei", Domain: config.Domain, Scope: config.scope("012345abcdef"), Environment: "012345abcdef", RunID: "e2e-12345678", Armed: true}
	manifest.Helper = "mca-dns-helper-012345abcdef"
	if err := manifest.validate(config); err != nil {
		t.Fatal(err)
	}
	for _, mutate := range []func(*cloudManifest){
		func(m *cloudManifest) { m.Scope = "run-012345abcdef.e2e-test-mc-attacker" },
		func(m *cloudManifest) { m.Domain = "other.top" },
		func(m *cloudManifest) { m.Environment = "../../escape" },
		func(m *cloudManifest) { m.Provider = "unrecognized" },
		func(m *cloudManifest) { m.Version = 0 },
	} {
		copy := manifest
		mutate(&copy)
		if err := copy.validate(config); err == nil {
			t.Fatalf("unsafe manifest accepted: %+v", copy)
		}
	}
}

func TestRecoveryAfterRuntimeLoss(t *testing.T) {
	for _, state := range []string{"success", "failure", "running", "locked"} {
		t.Run(state, func(t *testing.T) {
			directory := t.TempDir()
			config := providerConfig{Domain: "example.com", Prefix: "run", ManagedSubDomain: "e2e-test-mc", Region: "cn-north-4", AK: "private-ak", SK: "private-sk", TTL: 600}
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
		})
	}
}
