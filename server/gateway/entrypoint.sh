#!/bin/bash
#
# Start-up for the SigProfilerExtractor Workbench on a server: the launcher
# (../spe-workbench) runs this with the installed Python first on PATH.
#
# Runs the Workbench behind spe_gateway.py, which asks for this server's token
# and adds upload, .zip download and the resources panel. Everything the app
# keeps goes in $SPE_DATA:
#
#   uploads/                        files uploaded from the browser
#   SigProfilerExtractor_results/   default output folder for runs
#   references/                     reference genomes installed from the app
#   .cache/                         run records (settings and logs)
#   .workbench/token, url           the token and the link to open
#
# Settings (environment):
#   SPE_DATA         data folder                             (required)
#   SPE_PORT         port to listen on                       (default 8765)
#   SPE_PORT_TRIES   if it is taken, try the next ones, this many in all (default 1)
#   SPE_BIND         address to listen on                    (default 0.0.0.0)
#   SPE_TOKEN        use this token (32+ characters) instead of the stored one
#   SPE_HOST_NAME    the server's name, for the printed link and the panel
#   SPE_SSH_USER     user name for the printed SSH tunnel command
#   SPE_SSH_VIA      host to tunnel through, when the server itself is not
#                    reachable by SSH (a cluster's login node)
#   PYTHON_CPU_COUNT CPUs the runs may use                   (default all)
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${SPE_DATA:?SPE_DATA: the data folder}"
PORT="${SPE_PORT:-8765}"
STATE="${DATA}/.workbench"

if ! mkdir -p "${STATE}" 2>/dev/null || [[ ! -w "${DATA}" ]]; then
    echo "FATAL: ${DATA} is not writable by user $(id -u):$(id -g)." >&2
    exit 1
fi

# HOME and the caches in the data folder: results default to
# $HOME/SigProfilerExtractor_results, and run records to $XDG_CACHE_HOME.
export HOME="${DATA}"
export XDG_CACHE_HOME="${DATA}/.cache"
export MPLCONFIGDIR="${DATA}/.cache/matplotlib"
mkdir -p "${DATA}/uploads" "${DATA}/SigProfilerExtractor_results" "${DATA}/references" "${MPLCONFIGDIR}"

# One token per data folder, kept across restarts so the link can be
# bookmarked. Delete .workbench/token (spe-workbench new-token) for a new one.
TOKEN_FILE="${STATE}/token"
if [[ -n "${SPE_TOKEN:-}" ]]; then
    TOKEN="${SPE_TOKEN}"
elif [[ -s "${TOKEN_FILE}" ]]; then
    TOKEN="$(<"${TOKEN_FILE}")"
else
    TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
    (umask 077; printf '%s\n' "${TOKEN}" > "${TOKEN_FILE}")
fi
# Handed over in the environment: argv is visible to every user through ps.
export SPE_GATEWAY_TOKEN="${TOKEN}"
unset SPE_TOKEN

# The link (.workbench/url) is written, and printed, once the port is open.
rm -f "${STATE}/url"

exec python3 "${HERE}/spe_gateway.py" \
    --bind "${SPE_BIND:-0.0.0.0}" \
    --port "${PORT}" \
    --port-tries "${SPE_PORT_TRIES:-1}" \
    --url-file "${STATE}/url" \
    --public-host '*' \
    --uploads "${DATA}/uploads" \
    --volume "${DATA}/references"
