package dns

import (
	"context"
	"fmt"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
)

func cloudTraffic(ctx context.Context, t *engine.Scope) error {
	config, scope, err := prepareCloud(ctx, t, "huawei")
	if err != nil {
		return err
	}
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	if err = startRouter(ctx, t); err != nil {
		return err
	}
	motd, err := startTrafficServer(ctx, t, client)
	if err != nil {
		return err
	}
	server := fixtures.ServerOf(t.Env)
	ports := environment.Get[[]int](t.Env, "ports")
	base := "primary." + scope
	host := server.ID + "." + base + "." + config.Domain
	address := map[string]any{"type": "manual", "name": "primary", "record_type": "A", "value": "127.0.0.1", "port": ports[4]}
	dynamic := map[string]any{"enabled": true, "dns": config.application("huawei"), "managed_sub_domain": scope, "mc_router_base_url": routerEndpoint(t), "dns_ttl": config.TTL, "addresses": []any{address}}
	save := func() error {
		return client.JSON(ctx, "PUT", "/api/config/modules/dns", map[string]any{"config_data": dynamic}, nil, 200)
	}
	expected := func(ids ...string) (map[string]string, map[string]string) {
		records := map[string]string{"*." + base + "|A": "127.0.0.1"}
		routes := map[string]string{}
		for _, id := range ids {
			name := id + "." + base + "." + config.Domain
			records["_minecraft._tcp."+id+"."+base+"|SRV"] = fmt.Sprintf("0 5 %v %s", address["port"], name)
			gamePort := server.GamePort
			if id != server.ID {
				gamePort = ports[6]
			}
			routes[name] = fmt.Sprintf("localhost:%d", gamePort)
		}
		return records, routes
	}
	check := func(ids ...string) error {
		if err := waitClean(ctx, client); err != nil {
			return err
		}
		records, routes := expected(ids...)
		return checkState(ctx, t, client, records, routes, config.TTL)
	}
	if err = save(); err != nil {
		return err
	}
	if err = t.Step("server synchronization publishes DNS and routes actual Minecraft status traffic", func() error {
		if err := client.RunTask(ctx, "POST", "/api/servers/sync", map[string]any{"dry_run": false}, nil); err != nil {
			return err
		}
		if err := check(server.ID); err != nil {
			return err
		}
		if err := checkRecursive(ctx, t, host, ports[4]); err != nil {
			return err
		}
		if err := dnsTraffic(ctx, t, config, host, motd, ports[4]); err != nil {
			return err
		}
		if _, err := minecraftStatus(ctx, fmt.Sprintf("127.0.0.1:%d", ports[4]), "unknown."+base+"."+config.Domain, ports[4]); err == nil {
			return fmt.Errorf("unconfigured hostname reached Minecraft")
		}
		return nil
	}); err != nil {
		return err
	}
	if err = t.Step("application startup repairs a drifted live route", func() error {
		if _, err := routerRequest(ctx, t, "POST", "/routes", map[string]string{"serverAddress": host, "backend": "localhost:1"}); err != nil {
			return err
		}
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		if err := check(server.ID); err != nil {
			return err
		}
		return dnsTraffic(ctx, t, config, host, motd, ports[4])
	}); err != nil {
		return err
	}
	if err = t.Step("creating and removing a stopped server automatically reconciles its DNS and route", func() error {
		id := server.ID + "-extra"
		journal := environment.Get[*platform.Journal](t.Env, "journal")
		if err := journal.Track(t.Env.ID, "mc-"+id, ""); err != nil {
			return err
		}
		compose := fixtures.Compose(t.Env, id, fmt.Sprint(ports[6]), fmt.Sprint(ports[7]))
		compose = strings.Replace(compose, "name: e2e-"+t.Env.ID+"\n", "name: e2e-"+t.Env.ID+"-extra\n", 1)
		if err := client.RunTask(ctx, "POST", "/api/servers/"+id, map[string]any{"yaml_content": compose}, nil); err != nil {
			return err
		}
		if err := check(server.ID, id); err != nil {
			return err
		}
		if err := fixtures.Operation(ctx, client, id, "remove"); err != nil {
			return err
		}
		return check(server.ID)
	}); err != nil {
		return err
	}
	if err = t.Step("changing the router listener and SRV port preserves DNS-derived Minecraft traffic", func() error {
		journal := environment.Get[*platform.Journal](t.Env, "journal")
		if err := journal.Docker.RemoveOwned(ctx, "mca-e2e-"+t.Env.ID+"-router", journal.Manifest.RunID, t.Env.ID); err != nil {
			return err
		}
		ports[4], ports[5] = ports[5], ports[4]
		if err := startRouter(ctx, t); err != nil {
			return err
		}
		address["port"] = ports[4]
		if err := save(); err != nil {
			return err
		}
		if err := client.RunTask(ctx, "POST", "/api/dns/update", nil, nil); err != nil {
			return err
		}
		if err := check(server.ID); err != nil {
			return err
		}
		return dnsTraffic(ctx, t, config, host, motd, ports[4])
	}); err != nil {
		return err
	}
	return t.Step("stopping Minecraft retains the active server DNS and route", func() error {
		if err := fixtures.Operation(ctx, client, server.ID, "stop"); err != nil {
			return err
		}
		server.Running = false
		if err := client.RunTask(ctx, "POST", "/api/servers/sync", map[string]any{"dry_run": false}, nil); err != nil {
			return err
		}
		return check(server.ID)
	})
}
