#!/usr/bin/env bash
set -euo pipefail
repository=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
export PATH="$HOME/.local/bin:/usr/local/go/bin:$PATH"
binary="${MC_ADMIN_E2E_BINARY:-$HOME/.cache/mc-admin/e2e/mc-admin-e2e}"
output="${MC_ADMIN_E2E_OUTPUT:-$HOME/.local/share/mc-admin-e2e}"
case "$output" in
    /mnt/*) printf '%s\n' 'Owned E2E data requires Linux filesystem storage.' >&2; exit 2 ;;
    /*) ;;
    *) printf '%s\n' 'Owned E2E data requires an absolute Linux path.' >&2; exit 2 ;;
esac
action=${1:-help}
if (($#)); then shift; fi
case "$action" in
    build)
        mkdir -p -- "$(dirname -- "$binary")"
        cd -- "$repository/e2e"
        GIT_OPTIONAL_LOCKS=0 CGO_ENABLED=0 go build -trimpath -o "$binary" ./cmd/mc-admin-e2e
        ;;
    run)
        if [[ " $* " != *" --case "* && " $* " != *" --case="* ]]; then
            printf '%s\n' 'API E2E requires --case with explicit anchored case IDs.' >&2; exit 2
        fi
        cd -- "$repository/e2e"
        exec "$binary" run --output "$output" "$@"
        ;;
    browser)
        options=()
        while (($#)) && [[ "$1" != -- && "$1" != browser/*.spec.ts ]]; do options+=("$1"); shift; done
        if (($#)) && [[ "$1" == -- ]]; then shift; fi
        if (($# == 0)) || [[ "$1" != browser/*.spec.ts ]] || [[ " $* " != *" --grep "* && " $* " != *" --grep="* ]]; then
            printf '%s\n' 'Browser tests require -- browser/file.spec.ts --grep exact-title.' >&2; exit 2
        fi
        cd -- "$repository/frontend-react"
        exec "$binary" browser --output "$output" "${options[@]}" -- bash "$repository/scripts/dev/backend.sh" run python "$repository/scripts/dev/browser_bridge.py" "$@"
        ;;
    help) printf '%s\n' 'e2e.ps1 build | run --backend-image IMAGE --tag regression --case ^ID$ | browser --backend-image IMAGE -- browser/file.spec.ts --grep TITLE' ;;
    *) printf 'Unknown E2E action: %s\n' "$action" >&2; exit 2 ;;
esac
