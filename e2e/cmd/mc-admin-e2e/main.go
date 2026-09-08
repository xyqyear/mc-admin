package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"mc-admin/e2e/internal/coverage"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/evidence"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
	"mc-admin/e2e/suites"
)

func main() { os.Exit(mainCode(os.Args[1:])) }

func mainCode(args []string) int {
	if len(args) == 0 {
		args = []string{"run"}
	}
	if args[0] == "cleanup" {
		return cleanup(args[1:])
	}
	if args[0] == "coverage" {
		return auditCoverage(args[1:])
	}
	if args[0] != "run" && args[0] != "list" && args[0] != "plan" {
		fmt.Fprintln(os.Stderr, "usage: mc-admin-e2e run|list|plan|cleanup|coverage [options]")
		return 2
	}
	command := args[0]
	flags := flag.NewFlagSet(command, flag.ContinueOnError)
	var settings fixtures.Options
	var selection engine.Selection
	var workers int
	var output, runID, socket, shard string
	var noReuse bool
	var setupTimeout, cleanupTimeout, totalTimeout time.Duration
	flags.StringVar(&settings.Image, "backend-image", "", "application image built from the revision under test (required for run)")
	flags.StringVar(&settings.MinecraftImage, "minecraft-image", fixtures.DefaultMinecraftImage, "Minecraft image including java tag and digest")
	flags.StringVar(&settings.MinecraftVersion, "minecraft-version", fixtures.DefaultMinecraftVersion, "exact Minecraft version")
	flags.StringVar(&settings.ExternalConfig, "external-config", "", "private JSON configuration for explicitly selected external qualification cases")
	flags.StringVar(&settings.PortDirectory, "port-directory", filepath.Join(os.TempDir(), "mc-admin-e2e-ports"), "host-shared port lease directory; all concurrent runners must agree")
	flags.IntVar(&settings.MinecraftSlots, "mc-slots", 1, "maximum live Minecraft environments")
	flags.IntVar(&workers, "workers", 2, "maximum concurrent environments")
	flags.StringVar(&selection.Match, "case", "", "case ID regular expression")
	flags.StringVar(&selection.Suite, "suite", "", "domain suite")
	flags.StringVar(&selection.Tag, "tag", "smoke", "case tag; empty selects all tags")
	flags.StringVar(&shard, "shard", "1/1", "one-based INDEX/COUNT")
	flags.Uint64Var(&selection.Seed, "seed", 0, "reproducible shuffle seed; zero preserves catalog order")
	flags.StringVar(&output, "output", ".runs", "parent directory for reports and owned runtimes")
	flags.StringVar(&runID, "run-id", "", "unique run ID; defaults to a random ID")
	flags.StringVar(&socket, "docker-socket", "/var/run/docker.sock", "local Docker Unix socket")
	flags.BoolVar(&noReuse, "no-reuse", false, "create a fresh environment for every case")
	flags.DurationVar(&setupTimeout, "setup-timeout", 8*time.Minute, "per-environment provisioning deadline")
	flags.DurationVar(&cleanupTimeout, "cleanup-timeout", 2*time.Minute, "independent deadline for each cleanup, verification and diagnostic phase")
	flags.DurationVar(&totalTimeout, "timeout", 30*time.Minute, "overall execution deadline")
	if err := flags.Parse(args[1:]); err != nil {
		return 2
	}
	if flags.NArg() != 0 {
		fmt.Fprintln(os.Stderr, "unexpected positional arguments")
		return 2
	}
	parts := strings.Split(shard, "/")
	if len(parts) != 2 {
		fmt.Fprintln(os.Stderr, "shard must be INDEX/COUNT")
		return 2
	}
	var err error
	selection.ShardIndex, err = strconv.Atoi(parts[0])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	selection.ShardCount, err = strconv.Atoi(parts[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	if workers < 1 || settings.MinecraftSlots < 1 || setupTimeout <= 0 || cleanupTimeout <= 0 || totalTimeout <= 0 {
		fmt.Fprintln(os.Stderr, "resource budgets and timeouts must be positive")
		return 2
	}
	factory := fixtures.NewFactory(settings, nil, &evidence.Redactor{})
	plan, err := engine.BuildPlan(suites.Catalog(factory.Recipes()), selection)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	if command == "list" || command == "plan" {
		encoder := json.NewEncoder(os.Stdout)
		encoder.SetIndent("", "  ")
		if err := encoder.Encode(plan); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 2
		}
		return 0
	}
	if runtime.GOOS != "linux" {
		fmt.Fprintln(os.Stderr, "real deployment tests require Linux with a local Docker daemon")
		return 2
	}
	if settings.Image == "" {
		fmt.Fprintln(os.Stderr, "run requires --backend-image")
		return 2
	}
	if runID == "" {
		runID = "e2e-" + platform.ID()
	}
	socket, err = filepath.Abs(socket)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	docker := platform.Docker{Socket: socket}
	journal, err := platform.NewJournal(filepath.Join(output, runID), runID, docker, settings.Image)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	defer journal.Close()
	dir := journal.Manifest.Directory
	fmt.Println("Run directory:", dir)
	redactor := &evidence.Redactor{}
	signalCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	ctx, cancel := context.WithTimeout(signalCtx, totalTimeout)
	defer cancel()
	report := engine.Report{RunID: runID, Image: settings.Image, MinecraftImage: settings.MinecraftImage, MinecraftVersion: settings.MinecraftVersion, Started: time.Now().UTC(), Plan: plan, NoReuse: noReuse}
	if err = evidence.WriteJSON(filepath.Join(dir, "plan.json"), plan); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	prepareCtx, prepareCancel := context.WithTimeout(ctx, 10*time.Minute)
	err = docker.Preflight(prepareCtx)
	if err == nil {
		report.Image, err = docker.Image(prepareCtx, settings.Image)
	}
	if err == nil {
		err = journal.SetImage(report.Image)
	}
	if err == nil {
		for _, group := range plan.Groups {
			if group.Cases[0].Recipe.MinecraftSlots > 0 {
				if _, inspectErr := docker.Image(prepareCtx, settings.MinecraftImage); inspectErr != nil {
					fmt.Println("Preparing pinned Minecraft image...")
					_, err = docker.Run(prepareCtx, "pull", settings.MinecraftImage)
				}
				break
			}
		}
	}
	prepareCancel()
	if err != nil {
		report.Errors = append(report.Errors, err.Error())
		for _, group := range plan.Groups {
			for _, test := range group.Cases {
				report.Results = append(report.Results, engine.Result{ID: test.ID, Suite: test.Suite, Status: "failed", Started: time.Now().UTC(), Issues: []engine.Issue{{Phase: "setup", Message: err.Error()}}})
			}
		}
	} else {
		settings.Image = report.Image
		factory = fixtures.NewFactory(settings, journal, redactor)
		plan, err = engine.BuildPlan(suites.Catalog(factory.Recipes()), selection)
		if err != nil {
			report.Errors = append(report.Errors, err.Error())
		} else {
			var progressMu sync.Mutex
			report.Results = engine.Run(ctx, plan, factory, engine.Options{Workers: workers, NoReuse: noReuse, SetupTimeout: setupTimeout, CleanupTimeout: cleanupTimeout, Directory: dir, Redactor: redactor, Progress: func(message string) { progressMu.Lock(); defer progressMu.Unlock(); fmt.Println(message) }})
		}
	}
	cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), cleanupTimeout)
	if err = journal.Cleanup(cleanupCtx); err != nil {
		report.Errors = append(report.Errors, redactor.Text(err.Error()))
	}
	cleanupCancel()
	if err = ctx.Err(); err != nil {
		report.Errors = append(report.Errors, err.Error())
	}
	if err = report.Write(dir); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	for _, result := range report.Results {
		for _, issue := range result.Issues {
			fmt.Fprintf(os.Stderr, "%s [%s]: %s\n", result.ID, issue.Phase, issue.Message)
		}
	}
	for _, err := range report.Errors {
		fmt.Fprintln(os.Stderr, err)
	}
	fmt.Printf("Results: %s\n", filepath.Join(dir, "results.json"))
	if report.Failed() {
		return 1
	}
	return 0
}

func auditCoverage(args []string) int {
	flags := flag.NewFlagSet("coverage", flag.ContinueOnError)
	output := flags.String("output", "coverage", "directory for coverage.json and coverage.md")
	requireComplete := flags.Bool("require-complete", false, "fail unless all selected cases and shards have passed with trace evidence")
	requireObserved := flags.Bool("require-observed", false, "fail if any deployed API/WS operation has no recorded case observation")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if flags.NArg() == 0 || *output == "" {
		fmt.Fprintln(os.Stderr, "coverage requires one or more run directories and an output directory")
		return 2
	}
	summary, err := coverage.Write(flags.Args(), *output)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	fmt.Printf("Cases: %d/%d passed; operations with successful observations: %d/%d; report: %s\n", summary.PassedCases, summary.SelectedCases, summary.SuccessfulOperations, summary.OperationCount, filepath.Join(*output, "coverage.md"))
	if *requireComplete && (!summary.CasesComplete || !summary.ShardsComplete || !summary.AllCasesPassed || len(summary.MissingTraceCaseIDs) != 0) {
		fmt.Fprintln(os.Stderr, "coverage is incomplete or selected cases failed; see coverage.json")
		return 1
	}
	if *requireObserved && summary.UnobservedOperations != 0 {
		fmt.Fprintln(os.Stderr, "deployed API operations lack scenario observations; see coverage.json")
		return 1
	}
	return 0
}

func cleanup(args []string) int {
	flags := flag.NewFlagSet("cleanup", flag.ContinueOnError)
	dir := flags.String("run-dir", "", "run directory containing manifest.json")
	timeout := flags.Duration("timeout", 5*time.Minute, "cleanup deadline")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if *dir == "" || flags.NArg() != 0 || *timeout <= 0 {
		fmt.Fprintln(os.Stderr, "cleanup requires --run-dir and a positive timeout")
		return 2
	}
	journal, err := platform.OpenJournal(*dir)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	defer journal.Close()
	ctx, cancel := context.WithTimeout(context.Background(), *timeout)
	defer cancel()
	if err = journal.Cleanup(ctx); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	fmt.Println("Owned resources reclaimed:", journal.Manifest.RunID)
	return 0
}
