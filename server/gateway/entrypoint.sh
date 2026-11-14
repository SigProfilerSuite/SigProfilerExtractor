#!/bin/bash
#
# Container start-up for the SigProfilerExtractor Workbench (see ../Dockerfile).
#
# Runs the Workbench behind spe_gateway.py, which asks for this server's token
# and adds upload, .zip download and the resources panel. Everything the app
# keeps goes in $SPE_DATA (mount a folder there):
#
#   uploads/                        files uploaded from the browser
#   SigProfilerExtractor_results/   default output folder for runs
#   references/                     reference genomes installed from the app
#   .cache/                         run records (settings and logs)
#   .workbench/token, url           the token and the link to open
#
# Settings (environment):
#   SPE_DATA         data folder inside the container        (default /data)
#   SPE_PORT         port to listen on                       (default 8765)
#   SPE_BIND         address to listen on                    (default 0.0.0.0)
#   SPE_TOKEN        use this token (32+ characters) instead of the stored one
#   SPE_HOST_NAME    the server's name, for the printed link and the panel
#   SPE_PUBLIC_PORT  the port the browser uses, if mapped differently
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${SPE_DATA:-/data}"
PORT="${SPE_PORT:-8765}"
STATE="${DATA}/.workbench"

if ! mkdir -p "${STATE}" 2>/dev/null || [[ ! -w "${DATA}" ]]; then
    echo "FATAL: ${DATA} is not writable by user $(id -u):$(id -g)." >&2
    echo "       Mount a folder you own there, and run as yourself (docker run --user \$(id -u):\$(id -g))." >&2
    exit 1
fi

# HOME and the caches on the data folder: results default to
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

HOST="${SPE_HOST_NAME:-$(hostname -f 2>/dev/null || hostname)}"
URL="http://${HOST}:${SPE_PUBLIC_PORT:-${PORT}}/?token=${TOKEN}"
(umask 077; printf '%s\n' "${URL}" > "${STATE}/url")

cat <<EOF

  SigProfilerExtractor Workbench

  Open this link in your browser (keep it private: it is the key to this app):

    ${URL}

  If the port is not reachable from your computer, tunnel it over SSH and
  open the same link with localhost in place of ${HOST}:

    ssh -N -L ${SPE_PUBLIC_PORT:-${PORT}}:localhost:${SPE_PUBLIC_PORT:-${PORT}} ${SPE_SSH_USER:-you}@${HOST}

  Data folder: ${DATA}

EOF

exec python3 "${HERE}/spe_gateway.py" \
    --bind "${SPE_BIND:-0.0.0.0}" \
    --port "${PORT}" \
    --public-host '*' \
    --uploads "${DATA}/uploads" \
    --volume "${DATA}/references"
