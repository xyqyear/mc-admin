package platform

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestContainerOwnershipIsCheckedBeforeRemoval(t *testing.T) {
	dir := t.TempDir()
	marker := filepath.Join(dir, "removed")
	script := `#!/bin/sh
if [ "$3" = container ]; then
  printf '%s\n' '[{"Id":"actual-container-id","Config":{"Labels":{"io.mc-admin.e2e.run":"another-run","io.mc-admin.e2e.environment":"abcdef123456"}}}]'
else
  touch "$E2E_TEST_MARKER"
fi
`
	if err := os.WriteFile(filepath.Join(dir, "docker"), []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir+":"+os.Getenv("PATH"))
	t.Setenv("E2E_TEST_MARKER", marker)
	docker := Docker{Socket: "/unused.sock"}
	if err := docker.RemoveOwned(context.Background(), "reused-name", "owned-run", "abcdef123456"); err == nil {
		t.Fatal("ownership mismatch was accepted")
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatal("Docker mutation happened before ownership validation")
	}
	if err := docker.RemoveOwned(context.Background(), "owned-name", "another-run", "abcdef123456"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(marker); err != nil {
		t.Fatal("owned container was not removed")
	}
}

func TestDockerWarningsDoNotCorruptStructuredOutput(t *testing.T) {
	dir := t.TempDir()
	script := "#!/bin/sh\nprintf '%s\\n' 'warning or application stderr' >&2\nprintf '%s\\n' 'sha256:test'\nif [ \"$3\" = fail ]; then exit 1; fi\n"
	if err := os.WriteFile(filepath.Join(dir, "docker"), []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir+":"+os.Getenv("PATH"))
	docker := Docker{Socket: "/unused.sock"}
	got, err := docker.Image(context.Background(), "test")
	if err != nil || got != "sha256:test" {
		t.Fatalf("warning corrupted image identity: %q, %v", got, err)
	}
	got, err = docker.Run(context.Background(), "logs", "test")
	if err != nil || !strings.Contains(got, "application stderr") {
		t.Fatalf("lost application log diagnostics: %q, %v", got, err)
	}
	got, err = docker.Run(context.Background(), "fail")
	if err == nil || !strings.Contains(got, "application stderr") || !strings.Contains(err.Error(), "sha256:test") {
		t.Fatalf("lost failure diagnostics: %q, %v", got, err)
	}
}
