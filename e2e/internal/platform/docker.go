package platform

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

const RunLabel = "io.mc-admin.e2e.run"
const EnvLabel = "io.mc-admin.e2e.environment"

type Docker struct{ Socket string }

func ID() string {
	var data [6]byte
	if _, err := rand.Read(data[:]); err != nil {
		panic(err)
	}
	return hex.EncodeToString(data[:])
}

func (d Docker) Run(ctx context.Context, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, "docker", append([]string{"--host", "unix://" + d.Socket}, args...)...)
	cmd.WaitDelay = 3 * time.Second
	var output, diagnostics bytes.Buffer
	cmd.Stdout = &output
	cmd.Stderr = &diagnostics
	err := cmd.Run()
	if err != nil {
		combined := output.String() + diagnostics.String()
		return combined, fmt.Errorf("docker %s: %w: %s", args[0], err, strings.TrimSpace(combined))
	}
	if len(args) > 0 && args[0] == "logs" {
		return strings.TrimSpace(output.String() + diagnostics.String()), nil
	}
	return strings.TrimSpace(output.String()), nil
}

func (d Docker) Preflight(ctx context.Context) error {
	info, err := os.Stat(d.Socket)
	if err != nil {
		return fmt.Errorf("local Docker socket: %w", err)
	}
	if info.Mode()&os.ModeSocket == 0 {
		return fmt.Errorf("%s is not a Unix socket", d.Socket)
	}
	_, err = d.Run(ctx, "version", "--format", "{{.Server.Version}}")
	return err
}

func (d Docker) Image(ctx context.Context, reference string) (string, error) {
	return d.Run(ctx, "image", "inspect", reference, "--format", "{{.Id}}")
}

type Container struct {
	ID     string `json:"Id"`
	Image  string
	Config struct{ Labels map[string]string }
	State  struct {
		Status   string
		Running  bool
		ExitCode int
		Error    string
	}
	NetworkSettings struct {
		Ports map[string][]struct {
			HostIP   string `json:"HostIp"`
			HostPort string
		}
	}
}

func (d Docker) Inspect(ctx context.Context, name string) (*Container, error) {
	output, err := d.Run(ctx, "container", "inspect", name)
	if err != nil {
		if strings.Contains(output, "No such container") || strings.Contains(output, "No such object") {
			return nil, nil
		}
		return nil, err
	}
	var values []Container
	if err = json.Unmarshal([]byte(output), &values); err != nil {
		return nil, err
	}
	if len(values) != 1 {
		return nil, fmt.Errorf("expected one container for %s", name)
	}
	return &values[0], nil
}

func (d Docker) RemoveOwned(ctx context.Context, name, runID, envID string) error {
	container, err := d.Inspect(ctx, name)
	if err != nil || container == nil {
		return err
	}
	if container.Config.Labels[RunLabel] != runID || container.Config.Labels[EnvLabel] != envID {
		return fmt.Errorf("refusing to remove container %s: ownership mismatch", name)
	}
	_, err = d.Run(ctx, "rm", "-f", "-v", container.ID)
	return err
}
