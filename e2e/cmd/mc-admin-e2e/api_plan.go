package main

import (
	"crypto/sha256"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"mc-admin/e2e/internal/coverage"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/evidence"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/suites"
)

func runnerDigest() (string, error) {
	path, err := os.Executable()
	if err != nil {
		return "", err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", sha256.Sum256(data)), nil
}
func currentCatalog() []engine.Case {
	return suites.Catalog(fixtures.NewFactory(fixtures.Options{}, nil, &evidence.Redactor{}).Recipes())
}
func loadRunPlan(path string) (engine.RunPlan, error) {
	var plan engine.RunPlan
	data, err := os.ReadFile(path)
	if err != nil {
		return plan, err
	}
	err = json.Unmarshal(data, &plan)
	return plan, err
}
func restoredCosts(path, profile, compatibility string) (engine.CostProfile, json.RawMessage, error) {
	costs, err := suites.Costs()
	if err != nil {
		return costs, nil, err
	}
	costs.ShardOverheadSeconds = 1
	if path == "" {
		return costs, nil, nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintln(os.Stderr, "API history unavailable; using committed positive fallback")
		return costs, nil, nil
	}
	var envelope struct {
		SchemaVersion int                 `json:"schema_version"`
		Audited       bool                `json:"audited"`
		Component     string              `json:"component"`
		Profile       string              `json:"profile"`
		Compatibility string              `json:"compatibility"`
		Costs         *engine.CostProfile `json:"costs"`
		Source        json.RawMessage     `json:"source"`
		Artifact      json.RawMessage     `json:"artifact"`
	}
	if err = json.Unmarshal(data, &envelope); err != nil {
		fmt.Fprintln(os.Stderr, "Malformed API history; using committed positive fallback")
		return costs, nil, nil
	}
	if envelope.Costs == nil {
		var empty map[string]any
		if err = json.Unmarshal(data, &empty); err != nil || len(empty) != 0 {
			fmt.Fprintln(os.Stderr, "Malformed API history; using committed positive fallback")
		}
		return costs, nil, nil
	}
	var sourceFields map[string]json.RawMessage
	if err = json.Unmarshal(envelope.Source, &sourceFields); err != nil || len(sourceFields) == 0 || envelope.SchemaVersion != 1 || envelope.Component != "api" || !envelope.Audited || envelope.Profile != profile || envelope.Compatibility != compatibility {
		fmt.Fprintln(os.Stderr, "Incompatible API history; using committed positive fallback")
		return costs, nil, nil
	}
	old := *envelope.Costs
	if old.Measurement != "api-lifecycle-v2" {
		fmt.Fprintln(os.Stderr, "Incompatible API measurement; using committed positive fallback")
		return costs, nil, nil
	}
	if err = old.Validate(); err != nil {
		fmt.Fprintln(os.Stderr, "Invalid API history costs; using committed positive fallback")
		return costs, nil, nil
	}
	costs.DefaultSeconds = old.DefaultSeconds
	costs.Measurement = old.Measurement
	costs.Sources = old.Sources
	costs.ShardOverheadSeconds = old.ShardOverheadSeconds
	costs.Groups = old.Groups
	if costs.Cases == nil {
		costs.Cases = map[string]float64{}
	}
	if costs.Recipes == nil {
		costs.Recipes = map[string]float64{}
	}
	for key, value := range old.Cases {
		costs.Cases[key] = value
	}
	for key, value := range old.Recipes {
		costs.Recipes[key] = value
	}
	source, err := json.Marshal(map[string]json.RawMessage{"source": envelope.Source, "artifact": envelope.Artifact})
	return costs, source, err
}
func ciPlan(args []string) int {
	flags := flag.NewFlagSet("ci-plan", flag.ContinueOnError)
	var plan engine.RunPlan
	var history, output, githubOutput, compatibility string
	flags.StringVar(&plan.Profile, "profile", "regression", "current inventory profile; qualification requires Huawei")
	flags.StringVar(&plan.Revision, "revision", "", "candidate source SHA")
	flags.StringVar(&plan.Image, "backend-image", "", "candidate config digest")
	flags.StringVar(&history, "history", "", "frozen restored timing envelope")
	flags.StringVar(&compatibility, "compatibility", "", "stable fixture/resource fingerprint for historical costs")
	flags.StringVar(&output, "output", "api-plan.json", "immutable run-level plan")
	flags.StringVar(&githubOutput, "github-output", "", "Actions job output file")
	flags.BoolVar(&plan.NoReuse, "no-reuse", false, "create a Fresh environment for each case")
	flags.IntVar(&plan.Workers, "workers", 2, "concurrent environments per shard")
	flags.IntVar(&plan.MinecraftSlots, "mc-slots", 1, "Minecraft capacity per shard")
	flags.IntVar(&plan.MaxShards, "max-shards", 16, "bounded total shard count")
	flags.Float64Var(&plan.BudgetSeconds, "budget-seconds", 300, "soft lifecycle execution target")
	flags.Uint64Var(&plan.Seed, "seed", 0, "case execution shuffle seed")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if flags.NArg() != 0 || plan.Revision == "" || plan.Image == "" || output == "" {
		fmt.Fprintln(os.Stderr, "ci-plan requires revision, backend-image and output")
		return 2
	}
	var err error
	plan.RunnerSHA256, err = runnerDigest()
	historyProfile := plan.Profile
	if plan.NoReuse {
		historyProfile += "-no-reuse"
	}
	if err == nil {
		plan.Costs, plan.HistorySource, err = restoredCosts(history, historyProfile, compatibility)
	}
	if err == nil {
		plan, err = engine.BuildRunPlan(currentCatalog(), plan)
	}
	if err == nil {
		err = evidence.WriteJSON(output, plan)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	ordinary, huawei := []map[string]int{}, []map[string]int{}
	for _, shard := range plan.Shards {
		row := map[string]int{"shard": shard.Index, "count": len(plan.Shards)}
		if shard.Capability == "huawei" {
			huawei = append(huawei, row)
		} else {
			ordinary = append(ordinary, row)
		}
	}
	if githubOutput != "" {
		file, err := os.OpenFile(githubOutput, os.O_APPEND|os.O_WRONLY, 0600)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 2
		}
		normalJSON, _ := json.Marshal(map[string]any{"include": ordinary})
		cloudJSON, _ := json.Marshal(map[string]any{"include": huawei})
		_, err = fmt.Fprintf(file, "ordinary=%s\nhuawei=%s\ncloud=%t\nprofile=%s\n", normalJSON, cloudJSON, len(huawei) > 0, plan.Profile)
		closeErr := file.Close()
		if err != nil || closeErr != nil {
			fmt.Fprintln(os.Stderr, err, closeErr)
			return 2
		}
	}
	fmt.Printf("Immutable API plan %s: %d cases, %d shards, %d oversized groups\n", plan.Digest, len(plan.Catalog), len(plan.Shards), len(plan.Oversized))
	return 0
}
func ciAudit(args []string) int {
	flags := flag.NewFlagSet("ci-audit", flag.ContinueOnError)
	path := flags.String("plan", "", "immutable expected plan")
	profile := flags.String("profile", "regression", "independently required current inventory profile")
	revision := flags.String("revision", "", "candidate source SHA")
	image := flags.String("backend-image", "", "candidate config digest")
	output := flags.String("output", "coverage", "audit output directory")
	observed := flags.Bool("require-observed", false, "require deployed operation observations")
	noReuse := flags.Bool("no-reuse", false, "independently requested Fresh execution")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if *path == "" || flags.NArg() == 0 || *revision == "" || *image == "" {
		fmt.Fprintln(os.Stderr, "ci-audit requires plan, revision, backend-image and run directories")
		return 2
	}
	plan, err := loadRunPlan(*path)
	runner, runnerErr := runnerDigest()
	if err == nil && (runnerErr != nil || plan.Revision != *revision || plan.Image != *image || plan.RunnerSHA256 != runner || plan.NoReuse != *noReuse) {
		err = fmt.Errorf("expected plan differs from current candidate source/image/runner/execution policy")
	}
	var costs engine.CostProfile
	if err == nil {
		costs, err = coverage.AuditExpected(flags.Args(), plan, currentCatalog(), *profile)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	summary, err := coverage.Write(flags.Args(), *output)
	if err == nil && (!summary.CasesComplete || !summary.ShardsComplete || !summary.AllCasesPassed || len(summary.MissingTraceCaseIDs) > 0 || (*observed && summary.UnobservedOperations > 0)) {
		err = fmt.Errorf("API coverage or execution evidence is incomplete")
	}
	if err == nil {
		err = evidence.WriteJSON(filepath.Join(*output, "costs.json"), costs)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	fmt.Printf("Qualified %d current API cases against immutable plan %s\n", len(plan.Catalog), plan.Digest)
	return 0
}
