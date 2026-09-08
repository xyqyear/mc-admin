package world

import (
	"context"
	"fmt"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

// SIGSTOP leaves the real CLI and its repository behavior intact while assertions run.
const resticPauseObserver = `import os, signal, time
from pathlib import Path
root = Path('/tmp/e2e-restic-pauser')
root.mkdir(exist_ok=True)
(root / 'observer').write_text(str(os.getpid()))
paused = set()
def stop(*args):
    raise SystemExit()
signal.signal(signal.SIGTERM, stop)
(root / 'ready').touch()
try:
    for command in ('backup', 'ls'):
        found = False
        while not found:
            for process in Path('/proc').iterdir():
                if not process.name.isdigit():
                    continue
                try:
                    args = (process / 'cmdline').read_bytes().split(b'\0')
                    if not args or Path(os.fsdecode(args[0])).name != 'restic' or command.encode() not in args[1:]:
                        continue
                    pid = int(process.name)
                    os.kill(pid, signal.SIGSTOP)
                    paused.add(pid)
                    (root / command).write_text(str(pid))
                    found = True
                    break
                except (FileNotFoundError, ProcessLookupError, PermissionError):
                    continue
            if not found:
                time.sleep(.002)
        if command == 'backup':
            while not (root / 'resume-backup').exists():
                time.sleep(.01)
            os.kill(pid, signal.SIGCONT)
            paused.remove(pid)
        else:
            while Path('/proc', str(pid)).exists():
                time.sleep(.01)
finally:
    for pid in paused:
        try:
            os.kill(pid, signal.SIGCONT)
        except ProcessLookupError:
            pass
`

const resticPauseCleanup = `import os, signal
from pathlib import Path
root = Path('/tmp/e2e-restic-pauser')
for name in ('backup', 'ls'):
    marker = root / name
    if marker.exists():
        pid = int(marker.read_text())
        try:
            args = Path('/proc', str(pid), 'cmdline').read_bytes().split(b'\0')
            if Path(os.fsdecode(args[0])).name == 'restic':
                os.kill(pid, signal.SIGCONT)
        except (FileNotFoundError, ProcessLookupError):
            pass
marker = root / 'observer'
if marker.exists():
    pid = int(marker.read_text())
    try:
        if b'e2e-restic-pauser' in Path('/proc', str(pid), 'cmdline').read_bytes():
            os.kill(pid, signal.SIGTERM)
    except (FileNotFoundError, ProcessLookupError):
        pass
`

func startResticPauses(ctx context.Context, t *engine.Scope) error {
	backend := fixtures.BackendOf(t.Env)
	t.Cleanup(func(ctx context.Context) error {
		_, err := backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", resticPauseCleanup)
		return err
	})
	if _, err := backend.Docker.Run(ctx, "exec", "--detach", backend.Name, "python", "-c", resticPauseObserver); err != nil {
		return err
	}
	return waitResticPause(ctx, t, "ready")
}

func waitResticPause(ctx context.Context, t *engine.Scope, command string) error {
	backend := fixtures.BackendOf(t.Env)
	return api.Wait(ctx, 50*time.Millisecond, "owned Restic pause "+command, func(ctx context.Context) (bool, error) {
		output, err := backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", `import sys
from pathlib import Path
marker = Path('/tmp/e2e-restic-pauser', sys.argv[1])
if not marker.exists():
    print('waiting')
elif sys.argv[1] == 'ready':
    print('ready')
else:
    pid = marker.read_text()
    try:
        state = Path('/proc', pid, 'status').read_text().split('State:')[1].splitlines()[0]
        print('paused ' + pid if state.strip().startswith('T') else 'waiting')
    except FileNotFoundError:
        print('process-exited-before-pause')
`, command)
		if err != nil {
			return false, api.Permanent(err)
		}
		state := strings.TrimSpace(output)
		if state == "waiting" {
			return false, nil
		}
		if state != "ready" && !strings.HasPrefix(state, "paused ") {
			return false, api.Permanent(fmt.Errorf("Restic %s pause failed: %s", command, state))
		}
		t.Recorder.Event("fixture_process_pause", map[string]any{"command": command, "state": state})
		return true, nil
	})
}

func resumeResticBackup(ctx context.Context, t *engine.Scope) error {
	backend := fixtures.BackendOf(t.Env)
	_, err := backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", `from pathlib import Path; Path('/tmp/e2e-restic-pauser/resume-backup').touch()`)
	return err
}
