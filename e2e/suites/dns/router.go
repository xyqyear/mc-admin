package dns

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
)

const routerImage = "itzg/mc-router@sha256:e06735ea74877a7de649bcaec4cb917bf952564d32cbe258670fb7753192a1e9"
const routerURL = "http://127.0.0.1:26666"
const routerScript = `import json, sys, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
base, method, path = sys.argv[1:4]
body = sys.argv[4].encode() if len(sys.argv) > 4 else None
request = urllib.request.Request(base + path, data=body, headers={"Content-Type":"application/json","Accept":"application/json"}, method=method)
with opener.open(request, timeout=10) as response:
    raw = response.read()
    print(raw.decode() if raw else "{}")
`

func startRouter(ctx context.Context, t *engine.Scope) error {
	j := environment.Get[*platform.Journal](t.Env, "journal")
	if _, err := j.Docker.Image(ctx, routerImage); err != nil {
		if _, err = j.Docker.Run(ctx, "pull", routerImage); err != nil {
			return err
		}
	}
	name := "mca-e2e-" + t.Env.ID + "-router"
	if err := j.Track(t.Env.ID, name, ""); err != nil {
		return err
	}
	network := "container:" + fixtures.BackendOf(t.Env).Name
	apiBinding := "127.0.0.1:26666"
	routerArgs := []string{}
	if fixtures.BackendOf(t.Env).HostPort != 0 {
		ports := environment.Get[[]int](t.Env, "ports")
		network = "host"
		apiBinding = fmt.Sprintf("127.0.0.1:%d", ports[3])
		routerArgs = []string{"--port", fmt.Sprint(ports[4]), "--connection-rate-limit", "100", "--clients-to-allow", "127.0.0.1,::1"}
	}
	args := []string{"run", "-d", "--name", name, "--network", network, "--label", platform.RunLabel + "=" + j.Manifest.RunID, "--label", platform.EnvLabel + "=" + t.Env.ID, routerImage, "--api-binding", apiBinding}
	if _, err := j.Docker.Run(ctx, append(args, routerArgs...)...); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(t.Env.Dir, "dns-router.py"), []byte(routerScript), 0600); err != nil {
		return err
	}
	return api.Wait(ctx, 200*time.Millisecond, "owned mc-router HTTP readiness", func(ctx context.Context) (bool, error) {
		_, err := routerRequest(ctx, t, "GET", "/routes", nil)
		return err == nil, err
	})
}

func routerRequest(ctx context.Context, t *engine.Scope, method, path string, input any) (map[string]any, error) {
	args := []string{"exec", fixtures.BackendOf(t.Env).Name, "python", "/data/dns-router.py", routerEndpoint(t), method, path}
	if input != nil {
		data, err := json.Marshal(input)
		if err != nil {
			return nil, err
		}
		args = append(args, string(data))
	}
	output, err := fixtures.BackendOf(t.Env).Docker.Run(ctx, args...)
	if err != nil {
		return nil, err
	}
	var response map[string]any
	if err = json.Unmarshal([]byte(output), &response); err != nil {
		return nil, fmt.Errorf("decode owned router response: %w", err)
	}
	t.Recorder.Event("dns_router", map[string]any{"method": method, "path": path, "response": response})
	return response, nil
}

func routerEndpoint(t *engine.Scope) string {
	if fixtures.BackendOf(t.Env).HostPort != 0 {
		return fmt.Sprintf("http://127.0.0.1:%d", environment.Get[[]int](t.Env, "ports")[3])
	}
	return routerURL
}
