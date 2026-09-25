package world

import (
	"context"
	"fmt"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

const prunePauseObserver = ownedProcessSignals + `
import sys
root = Path('/tmp/e2e-prune-pauser')
root.mkdir()
project = Path(sys.argv[1])
write_identity(root / 'observer', owned_process(os.getpid()))
def stop(*args):
    raise SystemExit()
signal.signal(signal.SIGTERM, stop)
(root / 'ready').touch()
identity = None
try:
    deadline = time.monotonic() + 180
    while identity is None and not (root / 'resume').exists() and time.monotonic() < deadline:
        for process in Path('/proc').iterdir():
            if not process.name.isdigit():
                continue
            try:
                candidate = owned_process(process.name, 'mcmap', (b'prune-inhabited',))
                if candidate is None:
                    continue
                args = (process / 'cmdline').read_bytes().split(b'\0')
                if b'--dry-run' in args:
                    continue
                identity = candidate
                if not signal_owned(identity, signal.SIGSTOP):
                    identity = None
                    continue
                write_identity(root / 'paused', identity)
                break
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        time.sleep(.001)
    while identity is not None and not (root / 'resume').exists() and time.monotonic() < deadline:
        if owned_process(identity['pid']) != identity:
            (root / 'writer-ended').touch()
            break
        if not project.exists() and owned_process(identity['pid']) == identity:
            (root / 'deleted-before-writer-exit').touch()
        time.sleep(.01)
finally:
    signal_owned(identity, signal.SIGCONT)
`

func deletionWaitsForWriter(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "POST", s.base+"/operations", map[string]any{"action": "down"}, nil, 200); err != nil {
		return err
	}
	for index := range 256 {
		if err = s.seed(fmt.Sprintf("%s/r.%d.0.mca", fixtureRegion, index), regionData([2]string{"delete race", "delete race"})); err != nil {
			return err
		}
	}
	preview, err := s.prunePreview(ctx, "chunks", 1)
	if err != nil {
		return err
	}
	backend := fixtures.BackendOf(t.Env)
	if err = startPrunePause(ctx, s); err != nil {
		return err
	}
	var started struct {
		ID string `json:"task_id"`
	}
	if err = s.client.JSON(ctx, "POST", s.base+"/chunk-prune/apply", map[string]any{"preview_task_id": preview.ID}, &started, 200); err != nil {
		return err
	}
	if err = waitPrunePause(ctx, t, "paused"); err != nil {
		return err
	}
	deleteCtx, cancelDelete := context.WithCancel(ctx)
	defer cancelDelete()
	result := make(chan error, 1)
	var removed struct {
		ID        string   `json:"server_id"`
		Cancelled []string `json:"cancelled_background_task_ids"`
	}
	go func() {
		result <- s.client.JSON(deleteCtx, "POST", s.base+"/operations", map[string]any{"action": "remove"}, &removed, 200)
	}()
	if err = api.Wait(ctx, 50*time.Millisecond, "delete closes server write admission", func(ctx context.Context) (bool, error) {
		var state struct {
			Kind string `json:"kind"`
		}
		if err := s.client.JSON(ctx, "GET", s.base+"/maintenance", nil, &state, 200); err != nil {
			return false, api.Permanent(err)
		}
		return state.Kind == "remove", nil
	}); err != nil {
		return err
	}
	for _, request := range []struct {
		path string
		body any
	}{
		{s.base + "/files/content?path=/delete-race.txt", map[string]any{"content": "must not write"}},
		{s.base + "/files/ownership/restore", nil},
		{s.base + "/map/initialize", nil},
		{s.base + "/operations", map[string]any{"action": "start"}},
	} {
		if err = s.client.JSON(ctx, "POST", request.path, request.body, nil, 423); err != nil {
			return err
		}
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/map/tiles/0/0.png?region=world/region", nil, nil, 423); err != nil {
		return err
	}
	select {
	case err = <-result:
		if err != nil {
			return err
		}
	case <-ctx.Done():
		return ctx.Err()
	}
	if removed.ID != s.id || len(removed.Cancelled) != 1 || removed.Cancelled[0] != started.ID {
		return fmt.Errorf("deletion did not identify its cancelled writer: %+v", removed)
	}
	var task api.Task
	if err = s.client.JSON(ctx, "GET", "/api/tasks/"+started.ID, nil, &task, 200); err != nil {
		return err
	}
	if task.Status != "cancelled" {
		return fmt.Errorf("deletion returned before writer cancellation settled: %+v", task)
	}
	if err = waitPrunePause(ctx, t, "writer-ended"); err != nil {
		return err
	}
	if _, err = backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", ownedProcessSignals+`
root = Path('/tmp/e2e-prune-pauser')
identity = json.loads((root / 'paused').read_text())
assert owned_process(identity['pid']) != identity, 'deletion returned with its writer still alive'
assert not (root / 'deleted-before-writer-exit').exists(), 'project disappeared while its writer was alive'
`); err != nil {
		return err
	}
	var operations []struct {
		Kind           string     `json:"kind"`
		LegacyID       string     `json:"legacy_id"`
		State          string     `json:"state"`
		Phase          string     `json:"phase"`
		Ended          *time.Time `json:"ended_at"`
		WritersStopped bool       `json:"writers_stopped"`
	}
	if err = s.client.JSON(ctx, "GET", "/api/operations?limit=100", nil, &operations, 200); err != nil {
		return err
	}
	var writerEnded, deletionEnded *time.Time
	for _, operation := range operations {
		if operation.LegacyID == started.ID {
			if operation.State != "cancelled" || !operation.WritersStopped {
				return fmt.Errorf("writer history did not confirm safe cancellation: %+v", operation)
			}
			writerEnded = operation.Ended
		}
		if operation.Kind == "server_remove" {
			if operation.State != "succeeded" || operation.Phase != "server_removed" || !operation.WritersStopped {
				return fmt.Errorf("deletion history did not confirm completion: %+v", operation)
			}
			deletionEnded = operation.Ended
		}
	}
	if writerEnded == nil || deletionEnded == nil || writerEnded.After(*deletionEnded) {
		return fmt.Errorf("deletion history preceded writer settlement: writer=%v deletion=%v", writerEnded, deletionEnded)
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/compose", nil, nil, 404); err != nil {
		return err
	}
	return s.client.JSON(ctx, "GET", s.base+"/files/content?path=/delete-race.txt", nil, nil, 404)
}
