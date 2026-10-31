#!/usr/bin/env bash
set -euo pipefail

repository=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
export PATH="$HOME/.local/bin:$PATH"
export UV_PROJECT_ENVIRONMENT="${MC_ADMIN_LINUX_VENV:-$HOME/.venvs/mc-admin-backend}"
case "$UV_PROJECT_ENVIRONMENT" in
    /mnt/*|"$repository"/*) printf '%s\n' 'Linux virtual environment must be outside the Windows checkout.' >&2; exit 2 ;;
    /*) ;;
    *) printf '%s\n' 'Linux virtual environment requires an absolute path.' >&2; exit 2 ;;
esac
unset VIRTUAL_ENV
cd -- "$repository/backend"

action=${1:-help}
if (($#)); then shift; fi
case "$action" in
    sync)
        uv sync --locked
        exec uv run --locked python "$repository/scripts/dev/server.py" init
        ;;
    dev|debug|stop)
        exec uv run --locked python -Xfrozen_modules=off "$repository/scripts/dev/server.py" "$action" "$@"
        ;;
    test)
        selected=false
        for argument in "$@"; do
            file=${argument%%::*}
            if [[ "$file" == tests/*.py && -f "$file" ]]; then selected=true; fi
        done
        if [[ "$selected" != true ]]; then
            printf '%s\n' 'Select an explicit tests/...py file or pytest node ID.' >&2
            exit 2
        fi
        exec uv run --locked pytest "$@"
        ;;
    run)
        if (($# == 0)); then printf '%s\n' 'run requires a command.' >&2; exit 2; fi
        exec uv run --locked "$@"
        ;;
    help)
        printf '%s\n' 'backend.ps1 [sync|dev|debug|stop|test tests/file.py[::node]|run command ...]'
        ;;
    *) printf 'Unknown backend action: %s\n' "$action" >&2; exit 2 ;;
esac
