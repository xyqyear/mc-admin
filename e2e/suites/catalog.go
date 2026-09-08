package suites

import (
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/suites/archive"
	"mc-admin/e2e/suites/auth"
	"mc-admin/e2e/suites/cron"
	"mc-admin/e2e/suites/dns"
	"mc-admin/e2e/suites/files"
	"mc-admin/e2e/suites/minecraft"
	"mc-admin/e2e/suites/players"
	"mc-admin/e2e/suites/selfcheck"
	"mc-admin/e2e/suites/servers"
	"mc-admin/e2e/suites/snapshots"
	"mc-admin/e2e/suites/startup"
	"mc-admin/e2e/suites/system"
	"mc-admin/e2e/suites/tasks"
	"mc-admin/e2e/suites/templates"
	"mc-admin/e2e/suites/world"
)

func Catalog(recipes fixtures.Recipes) []engine.Case {
	var cases []engine.Case
	for _, suite := range []func(fixtures.Recipes) []engine.Case{auth.Cases, system.Cases, cron.Cases, selfcheck.Cases, templates.Cases, servers.Cases, files.Cases, archive.Cases, tasks.Cases, minecraft.Cases, players.Cases, snapshots.Cases, world.Cases, dns.Cases, startup.Cases} {
		cases = append(cases, suite(recipes)...)
	}
	for i := range cases {
		external, regression := false, false
		for _, tag := range cases[i].Tags {
			external = external || tag == "external"
			regression = regression || tag == "regression"
		}
		if !external && !regression {
			cases[i].Tags = append(cases[i].Tags, "regression")
		}
	}
	return cases
}
