#!/usr/bin/env bash
# Reusable POSIX launcher for the SigProfilerExtractor Workbench.
# Creates (or reuses) an isolated .venv-dashboard virtualenv next to this
# script, installs the package into it only when its dependency fingerprint
# changed, then starts the local Workbench server.
#
# Usage: ./launch_web.sh [--no-launch] [--reinstall] [--stop] [--volume PATH] [--help]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
LAUNCHER="$SCRIPT_DIR/SigProfilerExtractor/web/launcher.py"

has_flag() {
    local flag="$1"
    shift
    for arg in "$@"; do
        if [ "$arg" = "$flag" ]; then
            return 0
        fi
    done
    return 1
}

# --help and --stop never need a dependency install, so run them straight
# off the system interpreter without creating a venv first.
if has_flag --help "$@" || has_flag -h "$@"; then
    PY="$(command -v python3 || command -v python)"
    exec "$PY" "$LAUNCHER" --help
fi
if has_flag --stop "$@"; then
    PY="$(command -v python3 || command -v python)"
    exec "$PY" "$LAUNCHER" --stop
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Python 3 was not found on PATH. Install Python 3.9+ and try again." >&2
    exit 1
fi

VENV_DIR="$SCRIPT_DIR/.venv-dashboard"
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
VENV_PY="$VENV_DIR/bin/python"

REINSTALL_FLAG=""
if has_flag --reinstall "$@"; then
    REINSTALL_FLAG="--reinstall"
fi

# Run the fingerprint/install check by executing the file directly: the
# package is not necessarily installed into a brand-new venv yet, so this
# must work without `import SigProfilerExtractor` succeeding.
# (Plain string, not an array: macOS ships bash 3.2, which errors under
# `set -u` when expanding an empty array.)
"$VENV_PY" "$LAUNCHER" --ensure-deps-only $REINSTALL_FLAG

# The package is now installed in the venv; run the real dashboard as a
# proper module so its relative imports (server.py, jobs.py, ...) resolve.
exec "$VENV_PY" -m SigProfilerExtractor.web.launcher "$@"
