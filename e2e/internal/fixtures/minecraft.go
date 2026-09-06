package fixtures

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/platform"
)

type Server struct {
	ID                 string
	GamePort, RCONPort int
	Compose            string
	Running            bool
}

func ServerOf(env *environment.Environment) *Server { return environment.Get[*Server](env, "server") }

func Compose(env *environment.Environment, name, gamePort, rconPort string) string {
	options := environment.Get[Options](env, "options")
	journal := environment.Get[*platform.Journal](env, "journal")
	return fmt.Sprintf(`name: e2e-%s
services:
  mc:
    image: %q
    container_name: mc-%s
    labels:
      %s: %q
      %s: %q
    environment:
      EULA: 'true'
      VERSION: %q
      TYPE: VANILLA
      SERVER_PORT: '25565'
      ENABLE_RCON: 'true'
      RCON_PASSWORD: %q
      ONLINE_MODE: 'false'
      INIT_MEMORY: 256M
      MAX_MEMORY: 1G
      VIEW_DISTANCE: '2'
      SIMULATION_DISTANCE: '2'
      LEVEL_TYPE: minecraft:flat
      GENERATE_STRUCTURES: 'false'
      SPAWN_PROTECTION: '0'
      UID: '%d'
      GID: '%d'
    ports:
      - '127.0.0.1:%s:25565'
      - '127.0.0.1:%s:25575'
    volumes:
      - ./data:/data
    stdin_open: true
    tty: true
    restart: 'no'
`, env.ID, options.MinecraftImage, name, platform.RunLabel, journal.Manifest.RunID, platform.EnvLabel, env.ID, options.MinecraftVersion, BackendOf(env).Password, os.Getuid(), os.Getgid(), gamePort, rconPort)
}

func (f *Factory) server(ctx context.Context, env *environment.Environment) error {
	server := &Server{ID: "e2e-" + env.ID}
	env.Set("server", server)
	if err := f.Journal.Track(env.ID, "mc-"+server.ID, "e2e-"+env.ID); err != nil {
		return err
	}
	for attempt := 0; attempt < 3; attempt++ {
		ports := environment.Get[[]int](env, "ports")
		server.GamePort, server.RCONPort = ports[0], ports[1]
		server.Compose = Compose(env, server.ID, fmt.Sprint(server.GamePort), fmt.Sprint(server.RCONPort))
		err := BackendOf(env).Admin.JSON(ctx, "POST", "/api/servers/"+server.ID, map[string]any{"yaml_content": server.Compose}, nil, 200)
		if err == nil {
			break
		}
		var status *api.StatusError
		if attempt == 2 || !errors.As(err, &status) || status.Code != 409 || !strings.Contains(status.Body, "端口冲突") {
			return err
		}
		env.Recorder.Event("port_conflict", map[string]any{"attempt": attempt + 1, "ports": ports})
		if err = environment.Get[*platform.PortLease](env, "port-lease").Close(); err != nil {
			return err
		}
		if err = f.ports(ctx, env); err != nil {
			return err
		}
	}
	BackendOf(env).ServerIDs = append(BackendOf(env).ServerIDs, server.ID)
	return nil
}

func Operation(ctx context.Context, client *api.Client, id, action string) error {
	return client.JSON(ctx, "POST", "/api/servers/"+id+"/operations", map[string]string{"action": action}, nil, 200)
}

func Status(ctx context.Context, client *api.Client, id, expected string) error {
	var response struct {
		Status string `json:"status"`
	}
	if err := client.JSON(ctx, "GET", "/api/servers/"+id+"/status", nil, &response, 200); err != nil {
		return api.Permanent(err)
	}
	if !strings.EqualFold(response.Status, expected) {
		return fmt.Errorf("server %s status=%s, expected %s", id, response.Status, expected)
	}
	return nil
}

func WaitStatus(ctx context.Context, client *api.Client, id, expected string) error {
	return api.Wait(ctx, time.Second, "server "+id+" "+expected, func(ctx context.Context) (bool, error) {
		err := Status(ctx, client, id, expected)
		return err == nil, err
	})
}

func (f *Factory) running(ctx context.Context, env *environment.Environment) error {
	server := ServerOf(env)
	client := BackendOf(env).Admin
	if err := Operation(ctx, client, server.ID, "up"); err != nil {
		return err
	}
	if err := WaitStatus(ctx, client, server.ID, "healthy"); err != nil {
		return err
	}
	server.Running = true
	return nil
}

func verifyServer(ctx context.Context, env *environment.Environment) error {
	server := ServerOf(env)
	expected := "exists"
	if server.Running {
		expected = "healthy"
	}
	return Status(ctx, BackendOf(env).Admin, server.ID, expected)
}

func verifyRunning(ctx context.Context, env *environment.Environment) error {
	var response struct {
		Output string `json:"output"`
	}
	if err := BackendOf(env).Admin.JSON(ctx, "POST", "/api/servers/"+ServerOf(env).ID+"/rcon", map[string]string{"command": "list"}, &response, 200); err != nil {
		return err
	}
	if response.Output == "" {
		return fmt.Errorf("RCON readiness returned empty output")
	}
	return nil
}

func (f *Factory) restic(ctx context.Context, env *environment.Environment) error {
	_, err := f.Journal.Docker.Run(ctx, "exec", BackendOf(env).Name, "restic", "--repo", "/data/restic", "--insecure-no-password", "init")
	return err
}
