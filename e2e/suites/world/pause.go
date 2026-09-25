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

const ownedProcessSignals = `import json, os, signal, time
from pathlib import Path
owned_root = os.stat('/')
def write_identity(marker, identity):
    pending = marker.with_suffix('.tmp')
    pending.write_text(json.dumps(identity))
    pending.replace(marker)
def owned_process(pid, executable=None, required=()):
    try:
        process = Path('/proc', str(pid))
        process_root = (process / 'root').stat()
        if (process_root.st_dev, process_root.st_ino) != (owned_root.st_dev, owned_root.st_ino):
            return None
        args = (process / 'cmdline').read_bytes().split(b'\0')
        name = Path(os.fsdecode(args[0])).name
        if not name or (executable is not None and name != executable) or any(arg not in args[1:] for arg in required):
            return None
        started = (process / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        return {'pid': int(pid), 'started': started, 'executable': name}
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
def signal_owned(identity, signum):
    if identity is None:
        return False
    descriptor = None
    try:
        descriptor = os.pidfd_open(identity['pid'])
        if owned_process(identity['pid']) != identity:
            return False
        signal.pidfd_send_signal(descriptor, signum)
        return True
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
`

// SIGSTOP leaves the real CLI and its repository behavior intact while assertions run.
const resticPauseObserver = ownedProcessSignals + `
root = Path('/tmp/e2e-restic-pauser')
root.mkdir(exist_ok=True)
write_identity(root / 'observer', owned_process(os.getpid()))
paused = {}
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
                    identity = owned_process(process.name, 'restic', (command.encode(),))
                    if identity is None:
                        continue
                    pid = identity['pid']
                    paused[pid] = identity
                    if not signal_owned(identity, signal.SIGSTOP):
                        paused.pop(pid)
                        continue
                    write_identity(root / command, identity)
                    found = True
                    break
                except (FileNotFoundError, ProcessLookupError, PermissionError):
                    continue
            if not found:
                time.sleep(.002)
        if command == 'backup':
            while not (root / 'resume-backup').exists():
                time.sleep(.01)
            signal_owned(identity, signal.SIGCONT)
            paused.pop(pid)
        else:
            while owned_process(pid) == identity:
                time.sleep(.01)
finally:
    for identity in paused.values():
        signal_owned(identity, signal.SIGCONT)
`

const resticPauseCleanup = ownedProcessSignals + `
root = Path('/tmp/e2e-restic-pauser')
for name in ('backup', 'ls'):
    marker = root / name
    if marker.exists():
        signal_owned(json.loads(marker.read_text()), signal.SIGCONT)
marker = root / 'observer'
if marker.exists():
    signal_owned(json.loads(marker.read_text()), signal.SIGTERM)
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
		output, err := backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", `import json, sys
from pathlib import Path
marker = Path('/tmp/e2e-restic-pauser', sys.argv[1])
if not marker.exists():
    print('waiting')
elif sys.argv[1] == 'ready':
    print('ready')
else:
    pid = str(json.loads(marker.read_text())['pid'])
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
