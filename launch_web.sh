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

# Python 3.10 or newer. On 3.9 pip still installs reportlab 5.1 (the PDF
# library SigProfilerAssignment uses), which then refuses to import: the
# Workbench would open, and every run would fail with an ImportError.
MIN_PYTHON="3.10"

# Succeeds if the Python at $1 runs and is new enough.
python_ok() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

python_version() {
    "$1" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null || echo "unknown"
}

# The first new enough Python on PATH: the default python3 (or python), else
# a versioned one, so a Python installed from python.org, Homebrew or conda
# is found even when an older default comes first on PATH (the python3 that
# comes with macOS is 3.9).
find_python() {
    local name found
    for name in python3 python python3.14 python3.13 python3.12 python3.11 python3.10; do
        found="$(command -v "$name" 2>/dev/null)" || continue
        if python_ok "$found"; then
            echo "$found"
            return 0
        fi
    done
    return 1
}

# No new enough Python: say so in words someone who never uses a terminal
# can act on. (Terminal keeps the window open after a failed .command.)
no_python() {
    local old
    old="$(command -v python3 || command -v python || true)"
    {
        echo
        echo "The SigProfilerExtractor Workbench needs Python $MIN_PYTHON or newer."
        if [ -n "$old" ]; then
            echo "The Python on this computer is version $(python_version "$old") ($old), which is too old."
            if [ "$old" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ]; then
                echo "That is the Python that comes with macOS: leave it in place and install a newer one beside it."
            fi
        else
            echo "No Python was found on this computer."
        fi
        echo
        echo "Install the latest Python from https://www.python.org/downloads/"
        echo "and then open the Workbench again."
        echo
    } >&2
    exit 1
}

# --help and --stop never need a dependency install, so run them straight
# off the system interpreter without creating a venv first. Any Python 3
# can stop a Workbench or show the help.
if has_flag --help "$@" || has_flag -h "$@"; then
    PY="$(find_python || command -v python3 || command -v python)" || no_python
    exec "$PY" "$LAUNCHER" --help
fi
if has_flag --stop "$@"; then
    PY="$(find_python || command -v python3 || command -v python)" || no_python
    exec "$PY" "$LAUNCHER" --stop
fi

PYTHON_BIN="$(find_python)" || no_python

VENV_DIR="$SCRIPT_DIR/.venv-dashboard"
VENV_PY="$VENV_DIR/bin/python"
# An environment made with an older Python (before the launcher asked for
# 3.10) installs but cannot run an extraction, and one whose Python has been
# removed cannot run at all: stop any Workbench running from it, then make
# it again.
if [ -d "$VENV_DIR" ] && ! python_ok "$VENV_PY"; then
    MADE_WITH="$(python_version "$VENV_PY")"
    if [ "$MADE_WITH" = unknown ]; then
        echo "The Workbench's environment no longer runs; setting it up again with Python $(python_version "$PYTHON_BIN")."
    else
        echo "The Workbench's environment was made with Python $MADE_WITH; setting it up again with Python $(python_version "$PYTHON_BIN")."
    fi
    "$PYTHON_BIN" "$LAUNCHER" --stop >/dev/null 2>&1 || true
    rm -rf "$VENV_DIR"
fi
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

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
