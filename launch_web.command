#!/usr/bin/env bash
# macOS double-click launcher: Finder runs .command files in Terminal.app.
# This is a thin wrapper so the real logic lives in one place (launch_web.sh).
cd "$(dirname "$0")"
exec ./launch_web.sh "$@"
