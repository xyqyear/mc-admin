package fixtures

import (
	"context"
	"fmt"
	"path/filepath"

	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/platform"
)

func DeploymentCommand(ctx context.Context, env *environment.Environment, suffix string, command ...string) (string, error) {
	if len(command) == 0 {
		return "", fmt.Errorf("deployment command is empty")
	}
	journal := environment.Get[*platform.Journal](env, "journal")
	name := "mca-e2e-" + env.ID + "-" + suffix
	if err := journal.Track(env.ID, name, ""); err != nil {
		return "", err
	}
	args := []string{"run", "--rm", "--name", name,
		"--label", platform.RunLabel + "=" + journal.Manifest.RunID,
		"--label", platform.EnvLabel + "=" + env.ID,
		"--env-file", filepath.Join(env.Dir, "deployment.env"),
		"--mount", "type=bind,src=" + env.Dir + ",dst=/data",
		"--entrypoint", command[0], environment.Get[Options](env, "options").Image}
	args = append(args, command[1:]...)
	return journal.Docker.Run(ctx, args...)
}
