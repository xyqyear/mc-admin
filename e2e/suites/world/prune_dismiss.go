package world

import (
	"context"
	"fmt"
	"path/filepath"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func startPrunePause(ctx context.Context, s *scenario) error {
	backend := fixtures.BackendOf(s.t.Env)
	s.t.Cleanup(func(ctx context.Context) error {
		_, err := backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", ownedProcessSignals+`
root = Path('/tmp/e2e-prune-pauser')
if root.exists():
    (root / 'resume').touch()
    for name, sig in [('paused', signal.SIGCONT), ('observer', signal.SIGTERM)]:
        marker = root / name
        if marker.exists():
            signal_owned(json.loads(marker.read_text()), sig)
`)
		return err
	})
	if _, err := backend.Docker.Run(ctx, "exec", "--detach", backend.Name, "python", "-c", prunePauseObserver, filepath.Join(s.t.Env.Dir, "servers", s.id)); err != nil {
		return err
	}
	return waitPrunePause(ctx, s.t, "ready")
}

func waitPrunePause(ctx context.Context, t *engine.Scope, name string) error {
	backend := fixtures.BackendOf(t.Env)
	return api.Wait(ctx, 10*time.Millisecond, "owned prune pause "+name, func(ctx context.Context) (bool, error) {
		output, err := backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", ownedProcessSignals+`
import sys
marker = Path('/tmp/e2e-prune-pauser', sys.argv[1])
if not marker.exists():
    print('waiting')
elif sys.argv[1] in ('ready', 'writer-ended'):
    print('ready')
else:
    identity = json.loads(marker.read_text())
    assert owned_process(identity['pid']) == identity, 'owned prune process exited before observation'
    state = Path('/proc', str(identity['pid']), 'status').read_text().split('State:')[1].splitlines()[0]
    print('ready' if state.strip().startswith('T') else 'waiting')`, name)
		if err != nil {
			return false, api.Permanent(err)
		}
		return strings.TrimSpace(output) == "ready", nil
	})
}

func resumePrune(ctx context.Context, t *engine.Scope) error {
	backend := fixtures.BackendOf(t.Env)
	_, err := backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", ownedProcessSignals+`
root = Path('/tmp/e2e-prune-pauser')
identity = json.loads((root / 'paused').read_text())
assert owned_process(identity['pid']) == identity, 'cannot resume a replacement process'
(root / 'resume').touch()
assert signal_owned(identity, signal.SIGCONT), 'owned prune resume failed'
`)
	return err
}

func activePruneClaims(ctx context.Context, t *engine.Scope) (string, error) {
	backend := fixtures.BackendOf(t.Env)
	return backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", ownedProcessSignals+`
import hashlib
identity = json.loads(Path('/tmp/e2e-prune-pauser/paused').read_text())
assert owned_process(identity['pid']) == identity, 'claims observation requires the original active writer'
args = Path('/proc', str(identity['pid']), 'cmdline').read_bytes().split(b'\0')
claims = Path(os.fsdecode(args[args.index(b'--exclude-ftb-claims') + 1]))
payload = claims.read_bytes()
assert payload and json.loads(payload), 'active apply has no retained claim protection'
print(str(claims) + ':' + hashlib.sha256(payload).hexdigest())
`)
}

func pruneDismissActive(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.seedStoppedWorld(); err != nil {
		return err
	}
	if err = s.claims(); err != nil {
		return err
	}
	for index := 1; index < 256; index++ {
		if err = s.seed(fmt.Sprintf("%s/r.%d.0.mca", fixtureRegion, index), regionData([2]string{"dismiss zero", "dismiss one"})); err != nil {
			return err
		}
	}
	preview, err := s.prunePreview(ctx, "chunks", 3600)
	if err != nil {
		return err
	}
	if err = startPrunePause(ctx, s); err != nil {
		return err
	}
	var started struct {
		ID string `json:"task_id"`
	}
	if err = s.client.JSON(ctx, "POST", s.base+"/chunk-prune/apply", map[string]string{"preview_task_id": preview.ID}, &started, 200); err != nil {
		return err
	}
	if err = waitPrunePause(ctx, t, "paused"); err != nil {
		return err
	}
	claims, err := activePruneClaims(ctx, t)
	if err != nil {
		return err
	}
	if err = t.Step("dismissing a completed preview preserves artifacts leased by the active apply", func() error {
		if err := s.client.JSON(ctx, "DELETE", "/api/tasks/"+preview.ID, nil, nil, 200); err != nil {
			return err
		}
		if err := s.client.JSON(ctx, "GET", "/api/tasks/"+preview.ID, nil, nil, 404); err != nil {
			return err
		}
		retained, err := activePruneClaims(ctx, t)
		if err != nil {
			return err
		}
		if retained != claims {
			return fmt.Errorf("dismissing a preview changed its active apply's claims artifact")
		}
		t.Recorder.Event("active_prune_claims_retained", map[string]any{"preview_task_id": preview.ID, "apply_task_id": started.ID, "path_and_sha256": strings.TrimSpace(retained)})
		if err := s.client.JSON(ctx, "GET", s.base+"/chunk-prune/previews/"+preview.ID+"/geometry", nil, nil, 200); err != nil {
			return err
		}
		state, err := s.pruneState(ctx, preview.ID)
		if err != nil {
			return err
		}
		if state.PreviewTask == nil || state.PreviewTask.ID != preview.ID || state.ApplyTask == nil || state.ApplyTask.ID != started.ID {
			return fmt.Errorf("feature state lost dismissed preview or its active apply: %+v", state)
		}
		if err = s.pruneConflict(ctx, preview.ID, "prune_preview_consumed"); err != nil {
			return err
		}
		return s.client.JSON(ctx, "DELETE", "/api/tasks/"+started.ID, nil, nil, 400)
	}); err != nil {
		return err
	}
	if err = resumePrune(ctx, t); err != nil {
		return err
	}
	if _, err = s.client.Task(ctx, started.ID); err != nil {
		return fmt.Errorf("apply lost its preview artifacts after dismissal: %w", err)
	}
	claimed, _ := chunkPayload(regionData([2]string{"claimed", "unclaimed"}), 0)
	if err = s.checkChunk(ctx, 0, claimed); err != nil {
		return err
	}
	if err = s.checkChunk(ctx, 1, nil); err != nil {
		return err
	}
	if err = s.checkChunkAt(ctx, fixtureRegion+"/r.255.0.mca", 1, nil); err != nil {
		return err
	}
	return t.Step("restarting the backend does not reuse a previous process's preview artifacts", func() error {
		fresh, err := s.prunePreview(ctx, "regions", 3600)
		if err != nil {
			return err
		}
		if err = fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		if err = s.client.JSON(ctx, "GET", s.base+"/chunk-prune/previews/"+fresh.ID+"/geometry", nil, nil, 404); err != nil {
			return err
		}
		return s.client.JSON(ctx, "POST", s.base+"/chunk-prune/apply", map[string]string{"preview_task_id": fresh.ID}, nil, 404)
	})
}
