#!/usr/bin/env bash
# Remove what the SigProfilerExtractor Workbench installed on this Mac (or Linux computer):
#   - its private Python environment, .venv-dashboard, next to this script (with any
#     reference genome installed through the Workbench, which lives inside it)
#   - its run records, in ~/.cache/sigprofilerextractor
# Your results (wherever runs wrote them) and this SigProfilerExtractor folder are kept;
# delete them yourself if you no longer need them. Run it by double-clicking
# uninstall_web.command, or from Terminal: ./uninstall_web.sh [--yes]
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv-dashboard"
STATE="${XDG_CACHE_HOME:-$HOME/.cache}/sigprofilerextractor"
YES=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) YES=1 ;;
    -h|--help)
      echo "Usage: ./uninstall_web.sh [--yes]"
      echo "Removes the Workbench's Python environment ($VENV) and run records ($STATE)."
      echo "Results and this folder are kept. --yes removes without asking."
      exit 0 ;;
  esac
done

in_use() {
  # The Workbench, or one of its runs, still running?
  local pidfile="$STATE/dashboard.pid"
  if [ -f "$pidfile" ]; then
    local pid
    pid="$(cut -d: -f1 "$pidfile" 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then return 0; fi
  fi
  ps -axo command= 2>/dev/null | grep -F -- "$VENV/" | grep -F -- "SigProfilerExtractor.web" \
    | grep -v grep >/dev/null
}

echo
echo "  SigProfilerExtractor Workbench uninstaller"
echo "  ------------------------------------------"

if in_use; then
  echo "  The Workbench is still running. Click Quit in it (or run ./launch_web.sh --stop),"
  echo "  then run this again."
  exit 1
fi

HAS_VENV=0
[ -f "$VENV/pyvenv.cfg" ] && HAS_VENV=1
RUNS=0
[ -d "$STATE/jobs" ] && RUNS="$(find "$STATE/jobs" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
HAS_STATE=0
{ [ -d "$STATE/jobs" ] || [ -f "$STATE/dashboard.pid" ] || [ -f "$STATE/dashboard.lock" ]; } && HAS_STATE=1

if [ "$HAS_VENV" = 0 ] && [ "$HAS_STATE" = 0 ]; then
  echo "  Nothing to remove: the Workbench's Python environment and run records are not here."
  exit 0
fi

echo "  This removes:"
if [ "$HAS_VENV" = 1 ]; then
  SIZE="$(du -sh "$VENV" 2>/dev/null | cut -f1)"
  echo "    - the Python environment $VENV (${SIZE:-?})"
  GENOMES="$(ls -d "$VENV"/lib/python*/site-packages/SigProfilerMatrixGenerator/references/chromosomes/tsb/*/ 2>/dev/null \
    | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
  [ -n "$GENOMES" ] && echo "      including the reference genomes installed in it: $GENOMES"
fi
[ "$HAS_STATE" = 1 ] && echo "    - the records of $RUNS run(s) in $STATE (settings and logs, not results)"
echo
echo "  It keeps your results (each run's output folder, such as ~/SigProfilerExtractor_results)"
echo "  and this folder ($HERE)."
echo

if [ "$YES" = 0 ]; then
  read -r -p "  Remove them? Type y and press Enter: " ans
  case "$ans" in
    y|Y|yes|YES|Yes) ;;
    *) echo "  Nothing was removed."; exit 0 ;;
  esac
  echo
fi

status=0
if [ "$HAS_VENV" = 1 ]; then
  if rm -rf -- "$VENV"; then
    echo "  Removed $VENV."
  else
    echo "  Could not remove $VENV; delete that folder yourself."
    status=1
  fi
fi
if [ "$HAS_STATE" = 1 ]; then
  # Only the Workbench's own files; the folder goes only if that empties it.
  rm -rf -- "$STATE/jobs"
  rm -f -- "$STATE/dashboard.pid" "$STATE/dashboard.lock"
  rmdir "$STATE" 2>/dev/null || true
  if [ -d "$STATE/jobs" ]; then
    echo "  Could not remove the run records in $STATE; delete them yourself."
    status=1
  else
    echo "  Removed the run records."
  fi
fi

echo
echo "  Done. To start again later, double-click launch_web.command: it sets everything up anew."
echo "  To remove the rest, delete this folder and, if you no longer need them, your results."
exit $status
