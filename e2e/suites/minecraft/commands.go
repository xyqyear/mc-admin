package minecraft

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func commandTimeout(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	s := fixtures.ServerOf(t.Env)
	b := fixtures.BackendOf(t.Env)
	base := "/api/servers/" + s.ID
	run := func(ctx context.Context, script string) (string, error) {
		return b.Docker.Run(ctx, "exec", "mc-"+s.ID, "sh", "-c", script)
	}
	t.Cleanup(func(cleanup context.Context) error {
		_, err := run(cleanup, `if test -f /tmp/e2e-rcon-path; then p=$(cat /tmp/e2e-rcon-path); if test -f "$p.e2e-original"; then mv "$p.e2e-original" "$p"; fi; fi`)
		return err
	})
	_, err = run(ctx, `set -eu
p=$(command -v rcon-cli)
printf '%s' "$p" > /tmp/e2e-rcon-path
mv "$p" "$p.e2e-original"
cat > "$p" <<'SCRIPT'
#!/bin/sh
case "$1" in
  e2e-slow) echo call >> /tmp/e2e-rcon-calls; echo $$ > /tmp/e2e-rcon-pid; sleep 30 ;;
  e2e-fail) echo synthetic-private-stderr >&2; exit 23 ;;
  *) exec "$(cat /tmp/e2e-rcon-path).e2e-original" "$@" ;;
esac
SCRIPT
chmod +x "$p"`)
	if err != nil {
		return err
	}
	if err = t.Step("nonzero RCON exits return a safe 502", func() error {
		var failure struct {
			Detail string `json:"detail"`
		}
		if err := c.JSON(ctx, "POST", base+"/rcon", map[string]string{"command": "e2e-fail"}, &failure, 502); err != nil {
			return err
		}
		if strings.Contains(failure.Detail, "synthetic-private-stderr") || failure.Detail == "" {
			return fmt.Errorf("RCON error was not safely classified")
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("RCON deadline terminates the owned command once while monitoring remains available", func() error {
		requestCtx, cancel := context.WithCancel(ctx)
		defer cancel()
		result := make(chan error, 1)
		go func() {
			result <- c.JSON(requestCtx, "POST", base+"/rcon", map[string]string{"command": "e2e-slow"}, nil, 504)
		}()
		waitErr := api.Wait(ctx, 100*time.Millisecond, "owned RCON process starts", func(ctx context.Context) (bool, error) {
			out, err := run(ctx, `if test -f /tmp/e2e-rcon-pid; then echo ready; fi`)
			return strings.TrimSpace(out) == "ready", err
		})
		if waitErr == nil {
			probe, stop := context.WithTimeout(ctx, 2*time.Second)
			waitErr = c.JSON(probe, "GET", "/api/system/health", nil, nil, 200)
			if waitErr == nil {
				waitErr = c.JSON(probe, "GET", "/api/monitoring", nil, nil, 200)
			}
			stop()
		}
		if waitErr != nil {
			cancel()
		}
		requestErr := <-result
		if waitErr != nil {
			return waitErr
		}
		if requestErr != nil {
			return requestErr
		}
		out, err := run(ctx, `set -eu; test "$(wc -l < /tmp/e2e-rcon-calls)" -eq 1; p=$(cat /tmp/e2e-rcon-pid); test ! -e /proc/"$p"/stat || test "$(cut -d ' ' -f3 /proc/"$p"/stat)" = Z; echo cleaned`)
		if err != nil {
			return err
		}
		if strings.TrimSpace(out) != "cleaned" {
			return fmt.Errorf("RCON timed-out process cleanup was not observed")
		}
		return nil
	}); err != nil {
		return err
	}
	var output struct {
		Output string `json:"output"`
	}
	if err = c.JSON(ctx, "POST", base+"/rcon", map[string]string{"command": "list"}, &output, 200); err != nil {
		return err
	}
	if output.Output == "" {
		return fmt.Errorf("Minecraft RCON did not recover after timeout")
	}
	logs, err := b.Docker.Run(ctx, "logs", b.Name)
	if err != nil {
		return err
	}
	if strings.Contains(logs, "synthetic-private-stderr") {
		return fmt.Errorf("RCON diagnostic exposed stderr")
	}
	return nil
}
