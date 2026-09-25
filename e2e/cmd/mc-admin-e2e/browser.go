package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/evidence"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
)

type browserFixture struct {
	BaseURL          string `json:"base_url"`
	APIURL           string `json:"api_url"`
	ServerID         string `json:"server_id"`
	ServerPath       string `json:"server_path"`
	Username         string `json:"username"`
	Password         string `json:"password"`
	MasterToken      string `json:"master_token"`
	BackendContainer string `json:"backend_container"`
	RunID            string `json:"run_id"`
	EnvironmentID    string `json:"environment_id"`
	ImageID          string `json:"image_id"`
	ManifestPath     string `json:"manifest_path"`
}

func browser(args []string) int {
	flags := flag.NewFlagSet("browser", flag.ContinueOnError)
	var options fixtures.Options
	var output, runID, socket, recipeName string
	var timeout, setupTimeout, cleanupTimeout time.Duration
	flags.StringVar(&options.Image, "backend-image", "", "application image required for owned fixture")
	flags.StringVar(&options.MinecraftImage, "minecraft-image", fixtures.DefaultMinecraftImage, "pinned Minecraft image")
	flags.StringVar(&options.MinecraftVersion, "minecraft-version", fixtures.DefaultMinecraftVersion, "exact Minecraft version")
	flags.StringVar(&options.PortDirectory, "port-directory", filepath.Join(os.TempDir(), "mc-admin-e2e-ports"), "shared port lease directory")
	flags.StringVar(&output, "output", ".runs", "owned run parent directory")
	flags.StringVar(&runID, "run-id", "", "unique run identifier")
	flags.StringVar(&socket, "docker-socket", "/var/run/docker.sock", "local Docker socket")
	flags.StringVar(&recipeName, "recipe", "world", "world, backup, server or base")
	flags.DurationVar(&timeout, "timeout", 30*time.Minute, "fixture and child command deadline")
	flags.DurationVar(&setupTimeout, "setup-timeout", 8*time.Minute, "fixture preparation deadline")
	flags.DurationVar(&cleanupTimeout, "cleanup-timeout", 2*time.Minute, "independent cleanup budget")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if options.Image == "" || flags.NArg() == 0 || timeout <= 0 || setupTimeout <= 0 || cleanupTimeout <= 0 {
		fmt.Fprintln(os.Stderr, "browser requires --backend-image, positive deadlines and -- command [args...]")
		return 2
	}
	if recipeName != "world" && recipeName != "backup" && recipeName != "server" && recipeName != "base" {
		fmt.Fprintln(os.Stderr, "unknown fixture recipe:", recipeName)
		return 2
	}
	if runID == "" {
		runID = "browser-" + platform.ID()
	}
	options.MinecraftSlots = 1
	socket, err := filepath.Abs(socket)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	docker := platform.Docker{Socket: socket}
	journal, err := platform.NewJournal(filepath.Join(output, runID), runID, docker, options.Image)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	defer journal.Close()
	fmt.Println("Run directory:", journal.Manifest.Directory)
	redactor := &evidence.Redactor{}
	signalContext, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	ctx, cancel := context.WithTimeout(signalContext, timeout)
	defer cancel()
	var env *environment.Environment
	var release func()
	started := time.Now().UTC()
	execute := func() error {
		setup, cancelSetup := context.WithTimeout(ctx, setupTimeout)
		defer cancelSetup()
		if err := docker.Preflight(setup); err != nil {
			return err
		}
		image, err := docker.Image(setup, options.Image)
		if err != nil {
			return err
		}
		options.Image = image
		if err := journal.SetImage(image); err != nil {
			return err
		}
		factory := fixtures.NewFactory(options, journal, redactor)
		recipes := factory.Recipes()
		recipe := map[string]*environment.Recipe{"world": recipes.World, "backup": recipes.Backup, "server": recipes.Server, "base": recipes.Base}[recipeName]
		release, err = factory.Reserve(setup, recipe)
		if err != nil {
			return err
		}
		env, err = factory.New(setup, recipe)
		if err != nil {
			return err
		}
		backend := fixtures.BackendOf(env)
		access := browserFixture{BaseURL: backend.URL, APIURL: backend.URL + "/api", Username: "e2e-owner", Password: backend.Password, MasterToken: backend.Master, BackendContainer: backend.Name, RunID: runID, EnvironmentID: env.ID, ImageID: image, ManifestPath: filepath.Join(journal.Manifest.Directory, "manifest.json")}
		if recipeName != "base" {
			server := fixtures.ServerOf(env)
			access.ServerID = server.ID
			access.ServerPath = filepath.Join(env.Dir, "servers", server.ID)
		}
		data, err := json.MarshalIndent(access, "", "  ")
		if err != nil {
			return err
		}
		privatePath := filepath.Join(env.Dir, "browser.json")
		if err = os.WriteFile(privatePath, data, 0600); err != nil {
			return err
		}
		env.Recorder.Event("browser_fixture_ready", map[string]any{"image": image, "server": access.ServerID, "recipe": recipe.ID})
		return runBrowserCommand(ctx, flags.Args(), privatePath)
	}
	actionErr := environment.Protect(execute)
	cleanup, cancelCleanup := context.WithTimeout(context.Background(), cleanupTimeout)
	if env != nil {
		if actionErr != nil {
			actionErr = errors.Join(actionErr, journal.Capture(cleanup, env.ID, redactor))
		}
		actionErr = errors.Join(actionErr, env.Close(cleanup))
	}
	actionErr = errors.Join(actionErr, journal.Cleanup(cleanup))
	cancelCleanup()
	if release != nil {
		release()
	}
	result := map[string]any{"run_id": runID, "image_id": journal.Manifest.Image, "recipe": recipeName, "started_at": started, "finished_at": time.Now().UTC(), "success": actionErr == nil}
	if actionErr != nil {
		result["error"] = redactor.Text(actionErr.Error())
	}
	if err = evidence.WriteJSON(filepath.Join(journal.Manifest.Directory, "fixture-result.json"), result); err != nil {
		actionErr = errors.Join(actionErr, err)
	}
	if actionErr != nil {
		fmt.Fprintln(os.Stderr, redactor.Text(actionErr.Error()))
		return 1
	}
	return 0
}

type commandIdentity struct {
	start string
	group int
	state string
}

func readCommandIdentity(pid int) (commandIdentity, error) {
	data, err := os.ReadFile(fmt.Sprintf("/proc/%d/stat", pid))
	if err != nil {
		return commandIdentity{}, err
	}
	suffix := strings.LastIndexByte(string(data), ')')
	if suffix < 0 {
		return commandIdentity{}, fmt.Errorf("invalid child process identity")
	}
	fields := strings.Fields(string(data)[suffix+1:])
	if len(fields) < 20 {
		return commandIdentity{}, fmt.Errorf("incomplete child process identity")
	}
	group, err := strconv.Atoi(fields[2])
	if err != nil {
		return commandIdentity{}, err
	}
	return commandIdentity{state: fields[0], group: group, start: fields[19]}, nil
}

func signalOwnedCommand(pid int, identity commandIdentity, signal syscall.Signal) error {
	current, err := readCommandIdentity(pid)
	if err != nil {
		return err
	}
	if current.start != identity.start || current.group != pid {
		return fmt.Errorf("child process ownership changed")
	}
	err = syscall.Kill(-pid, signal)
	if errors.Is(err, syscall.ESRCH) {
		return nil
	}
	return err
}

func liveCommandGroup(group int) (bool, error) {
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return false, err
	}
	for _, entry := range entries {
		pid, err := strconv.Atoi(entry.Name())
		if err != nil {
			continue
		}
		identity, err := readCommandIdentity(pid)
		if errors.Is(err, os.ErrNotExist) || errors.Is(err, os.ErrPermission) {
			continue
		}
		if err != nil {
			return false, err
		}
		if identity.group == group && identity.state != "Z" && identity.state != "X" {
			return true, nil
		}
	}
	return false, nil
}

func runBrowserCommand(ctx context.Context, args []string, fixturePath string) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	command := exec.Command(args[0], args[1:]...)
	command.Env = append(os.Environ(), "MC_ADMIN_BROWSER_FIXTURE="+fixturePath)
	command.Stdin = os.Stdin
	command.Stdout = os.Stdout
	command.Stderr = os.Stderr
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := command.Start(); err != nil {
		return err
	}
	identity, err := readCommandIdentity(command.Process.Pid)
	if err != nil {
		_ = command.Process.Kill()
		return errors.Join(err, command.Wait())
	}
	ticker := time.NewTicker(25 * time.Millisecond)
	defer ticker.Stop()
	var interrupted error
running:
	for {
		current, err := readCommandIdentity(command.Process.Pid)
		if err != nil {
			interrupted = err
			break
		}
		if current.state == "Z" || current.state == "X" {
			break
		}
		select {
		case <-ctx.Done():
			interrupted = ctx.Err()
			break running
		case <-ticker.C:
		}
	}
	// Keep the leader unreaped until its group is drained, preventing PID/group reuse.
	cleanupErr := signalOwnedCommand(command.Process.Pid, identity, syscall.SIGTERM)
	deadline := time.Now().Add(5 * time.Second)
	for cleanupErr == nil {
		alive, err := liveCommandGroup(command.Process.Pid)
		if err != nil {
			cleanupErr = err
			break
		}
		if !alive {
			break
		}
		if time.Now().After(deadline) {
			cleanupErr = signalOwnedCommand(command.Process.Pid, identity, syscall.SIGKILL)
			stopDeadline := time.Now().Add(5 * time.Second)
			for cleanupErr == nil {
				alive, err := liveCommandGroup(command.Process.Pid)
				if err != nil {
					cleanupErr = err
					break
				}
				if !alive {
					break
				}
				if time.Now().After(stopDeadline) {
					cleanupErr = fmt.Errorf("owned command writers did not stop after termination")
					break
				}
				<-ticker.C
			}
			break
		}
		<-ticker.C
	}
	return errors.Join(interrupted, cleanupErr, command.Wait())
}
