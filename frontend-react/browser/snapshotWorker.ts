import { spawn } from 'node:child_process'
import type { OwnedEnvironment } from './fixtures'

const holdBackup = String.raw`
import os, pathlib, select, signal, sys, time
until = time.monotonic() + 45
command = sys.argv[1].encode()
owner_root = pathlib.Path('/proc/self/root').stat()
def owned_root(entry):
    root = (entry / 'root').stat()
    return (root.st_dev, root.st_ino) == (owner_root.st_dev, owner_root.st_ino)
while time.monotonic() < until:
    if select.select([sys.stdin], [], [], 0)[0]:
        sys.exit(0)
    for entry in pathlib.Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if not owned_root(entry):
                continue
            args = (entry / 'cmdline').read_bytes().split(b'\0')
            if not args or args[0] != b'/usr/local/bin/restic' or command not in args:
                continue
            handle = os.pidfd_open(int(entry.name))
            try:
                if not owned_root(entry) or (entry / 'cmdline').read_bytes().split(b'\0') != args:
                    continue
                signal.pidfd_send_signal(handle, signal.SIGSTOP)
                try:
                    print('held', flush=True)
                    select.select([sys.stdin], [], [], 60)
                finally:
                    signal.pidfd_send_signal(handle, signal.SIGCONT)
            finally:
                os.close(handle)
            sys.exit(0)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    time.sleep(0.005)
raise RuntimeError('The owned snapshot backup worker did not appear')
`

function holdSnapshotProcess(owned: OwnedEnvironment, command: 'backup' | 'restore') {
  const child = spawn('docker', ['exec', '-i', owned.backend_container, 'python', '-u', '-c', holdBackup, command], { stdio: 'pipe' })
  let stderr = ''
  child.stderr.on('data', chunk => { stderr += String(chunk) })
  let held = false
  let resolveHeld!: () => void
  let rejectHeld!: (reason: Error) => void
  const ready = new Promise<void>((resolve, reject) => { resolveHeld = resolve; rejectHeld = reject })
  void ready.catch(() => {})
  child.stdout.on('data', chunk => { if (String(chunk).includes('held')) { held = true; resolveHeld() } })
  const closed = new Promise<void>((resolve, reject) => {
    child.on('error', error => { rejectHeld(error); reject(error) })
    child.on('close', code => {
      if (!held) rejectHeld(new Error('Snapshot worker was not held: ' + stderr))
      if (code === 0) resolve()
      else reject(new Error(`Owned snapshot hold exited ${code}: ${stderr}`))
    })
  })
  void closed.catch(() => {})
  return { ready, release: async () => { child.stdin.end(); await closed } }
}

export const holdSnapshotBackup = (owned: OwnedEnvironment) => holdSnapshotProcess(owned, 'backup')
export const holdSnapshotRestore = (owned: OwnedEnvironment) => holdSnapshotProcess(owned, 'restore')
