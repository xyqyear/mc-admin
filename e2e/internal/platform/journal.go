package platform

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"

	"mc-admin/e2e/internal/evidence"
)

var validID = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{7,47}$`)
var validEnv = regexp.MustCompile(`^[a-f0-9]{12}$`)

type EnvironmentRecord struct {
	ID         string   `json:"id"`
	Containers []string `json:"containers"`
	Projects   []string `json:"projects"`
	Cleaned    bool     `json:"cleaned"`
}

type Manifest struct {
	Version      int                  `json:"version"`
	RunID        string               `json:"run_id"`
	Directory    string               `json:"directory"`
	Socket       string               `json:"docker_socket"`
	Image        string               `json:"image"`
	Environments []*EnvironmentRecord `json:"environments"`
}

type Journal struct {
	mu       sync.Mutex
	Manifest Manifest
	Docker   Docker
	lock     *Lock
}

func NewJournal(dir, runID string, docker Docker, image string) (*Journal, error) {
	if !validID.MatchString(runID) {
		return nil, fmt.Errorf("run ID must contain 8–48 lowercase letters, digits or hyphens")
	}
	abs, err := filepath.Abs(dir)
	if err != nil {
		return nil, err
	}
	if err = os.MkdirAll(filepath.Dir(abs), 0700); err != nil {
		return nil, err
	}
	parent, err := filepath.EvalSymlinks(filepath.Dir(abs))
	if err != nil {
		return nil, err
	}
	abs = filepath.Join(parent, filepath.Base(abs))
	if err = os.Mkdir(abs, 0700); err != nil {
		return nil, fmt.Errorf("run directory must be new: %w", err)
	}
	lock, err := TryLock(filepath.Join(abs, "active.lock"))
	if err != nil {
		return nil, err
	}
	j := &Journal{Docker: docker, lock: lock, Manifest: Manifest{Version: 1, RunID: runID, Directory: abs, Socket: docker.Socket, Image: image}}
	if err = j.save(); err != nil {
		lock.Close()
		return nil, err
	}
	for _, name := range []string{"runtime", "environments", "cases"} {
		if err = os.Mkdir(filepath.Join(abs, name), 0700); err != nil {
			lock.Close()
			return nil, err
		}
	}
	return j, nil
}

func OpenJournal(dir string) (*Journal, error) {
	abs, err := filepath.Abs(dir)
	if err != nil {
		return nil, err
	}
	real, err := filepath.EvalSymlinks(abs)
	if err != nil {
		return nil, err
	}
	if real != abs {
		return nil, fmt.Errorf("cleanup requires a canonical directory without symlinks")
	}
	lock, err := TryLock(filepath.Join(abs, "active.lock"))
	if err != nil {
		return nil, err
	}
	fail := func(err error) (*Journal, error) { lock.Close(); return nil, err }
	data, err := os.ReadFile(filepath.Join(abs, "manifest.json"))
	if err != nil {
		return fail(err)
	}
	var manifest Manifest
	if err = json.Unmarshal(data, &manifest); err != nil {
		return fail(err)
	}
	if manifest.Version != 1 || manifest.Directory != abs || !validID.MatchString(manifest.RunID) {
		return fail(fmt.Errorf("invalid ownership manifest"))
	}
	for _, record := range manifest.Environments {
		if !validEnv.MatchString(record.ID) {
			return fail(fmt.Errorf("invalid environment ID"))
		}
		for _, project := range record.Projects {
			if project != "e2e-"+record.ID {
				return fail(fmt.Errorf("invalid project ownership"))
			}
		}
	}
	return &Journal{Manifest: manifest, Docker: Docker{Socket: manifest.Socket}, lock: lock}, nil
}

func (j *Journal) Close() error { return j.lock.Close() }

func (j *Journal) SetImage(image string) error {
	j.mu.Lock()
	defer j.mu.Unlock()
	j.Manifest.Image = image
	return j.save()
}
func (j *Journal) save() error {
	return evidence.WriteJSON(filepath.Join(j.Manifest.Directory, "manifest.json"), j.Manifest)
}

func (j *Journal) AddEnvironment(id string) error {
	j.mu.Lock()
	defer j.mu.Unlock()
	if !validEnv.MatchString(id) {
		return fmt.Errorf("invalid environment ID")
	}
	j.Manifest.Environments = append(j.Manifest.Environments, &EnvironmentRecord{ID: id})
	return j.save()
}

func (j *Journal) Track(id, container, project string) error {
	j.mu.Lock()
	defer j.mu.Unlock()
	for _, record := range j.Manifest.Environments {
		if record.ID == id {
			if container != "" {
				record.Containers = append(record.Containers, container)
			}
			if project != "" {
				record.Projects = append(record.Projects, project)
			}
			return j.save()
		}
	}
	return fmt.Errorf("unknown environment %s", id)
}

func (j *Journal) Record(id string) (EnvironmentRecord, error) {
	j.mu.Lock()
	defer j.mu.Unlock()
	for _, record := range j.Manifest.Environments {
		if record.ID == id {
			copy := *record
			copy.Containers = append([]string(nil), record.Containers...)
			copy.Projects = append([]string(nil), record.Projects...)
			return copy, nil
		}
	}
	return EnvironmentRecord{}, fmt.Errorf("unknown environment %s", id)
}

func (j *Journal) Capture(ctx context.Context, id string, redactor *evidence.Redactor) error {
	record, err := j.Record(id)
	if err != nil {
		return err
	}
	dir := filepath.Join(j.Manifest.Directory, "environments", id)
	if err = os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	var errs []error
	for _, name := range record.Containers {
		container, err := j.Docker.Inspect(ctx, name)
		if err != nil {
			errs = append(errs, err)
			continue
		}
		if container == nil {
			continue
		}
		if container.Config.Labels[RunLabel] != j.Manifest.RunID || container.Config.Labels[EnvLabel] != id {
			errs = append(errs, fmt.Errorf("capture ownership mismatch: %s", name))
			continue
		}
		output, err := j.Docker.Run(ctx, "logs", "--tail", "300", container.ID)
		if err != nil {
			errs = append(errs, err)
		}
		if err = os.WriteFile(filepath.Join(dir, container.ID[:12]+".log"), []byte(redactor.Text(output)), 0600); err != nil {
			errs = append(errs, err)
		}
		if err = evidence.WriteJSON(filepath.Join(dir, container.ID[:12]+".json"), container); err != nil {
			errs = append(errs, err)
		}
	}
	return errors.Join(errs...)
}

func (j *Journal) CleanupEnvironment(ctx context.Context, id string) error {
	record, err := j.Record(id)
	if err != nil {
		return err
	}
	if record.Cleaned {
		return nil
	}
	var errs []error
	for _, name := range record.Containers {
		if err := j.Docker.RemoveOwned(ctx, name, j.Manifest.RunID, id); err != nil {
			errs = append(errs, err)
		}
	}
	if len(errs) > 0 {
		return errors.Join(errs...)
	}
	output, err := j.Docker.Run(ctx, "ps", "-aq", "--filter", "label="+RunLabel+"="+j.Manifest.RunID, "--filter", "label="+EnvLabel+"="+id)
	if err != nil {
		return err
	}
	for _, name := range strings.Fields(output) {
		if err := j.Docker.RemoveOwned(ctx, name, j.Manifest.RunID, id); err != nil {
			errs = append(errs, err)
		}
	}
	for _, project := range record.Projects {
		output, err := j.Docker.Run(ctx, "network", "ls", "-q", "--filter", "label=com.docker.compose.project="+project)
		if err != nil {
			errs = append(errs, err)
			continue
		}
		for _, network := range strings.Fields(output) {
			if _, err = j.Docker.Run(ctx, "network", "rm", network); err != nil {
				errs = append(errs, err)
			}
		}
	}
	if len(errs) > 0 {
		return errors.Join(errs...)
	}
	dir := filepath.Join(j.Manifest.Directory, "runtime", id)
	if info, err := os.Lstat(dir); err == nil && info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("refusing symlink runtime directory")
	}
	if err = os.RemoveAll(dir); err != nil {
		helper := "mca-e2e-" + id + "-cleanup"
		if err = j.Track(id, helper, ""); err != nil {
			return err
		}
		_, err = j.Docker.Run(ctx, "run", "--rm", "--name", helper, "--label", RunLabel+"="+j.Manifest.RunID, "--label", EnvLabel+"="+id,
			"--mount", "type=bind,src="+dir+",dst=/cleanup", "--entrypoint", "chown", j.Manifest.Image, "-R", fmt.Sprintf("%d:%d", os.Getuid(), os.Getgid()), "/cleanup")
		if err != nil {
			return err
		}
		if err = os.RemoveAll(dir); err != nil {
			return err
		}
	}
	j.mu.Lock()
	defer j.mu.Unlock()
	for _, record := range j.Manifest.Environments {
		if record.ID == id {
			record.Cleaned = true
		}
	}
	return j.save()
}

func (j *Journal) Cleanup(ctx context.Context) error {
	j.mu.Lock()
	var ids []string
	for _, r := range j.Manifest.Environments {
		ids = append(ids, r.ID)
	}
	j.mu.Unlock()
	var errs []error
	for _, id := range ids {
		if err := j.CleanupEnvironment(ctx, id); err != nil {
			errs = append(errs, fmt.Errorf("environment %s: %w", id, err))
		}
	}
	return errors.Join(errs...)
}
