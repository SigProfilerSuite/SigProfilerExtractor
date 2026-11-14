#!/bin/bash
#
# run_workbench.sbatch -- the SigProfilerExtractor Workbench on a DGX node,
# used from the browser on your own computer.
#
#   sbatch run_workbench.sbatch
#   cat workbench_endpoint.env        # URL with token, once the job is running
#   scancel -n spe_workbench          # stop it (or Quit in the Workbench)
#
# Upload inputs, start runs, follow them, explore results and download them,
# all from the browser. spe_gateway.py puts a token check in front of the
# Workbench (it has no login of its own) and adds upload and .zip download.
#
# Runs started from the Workbench live inside this job: when the job ends
# (Quit, scancel, time limit or preemption), any unfinished run is stopped.
# Size --time to your longest run.
#
#SBATCH --job-name=spe_workbench
#SBATCH --partition=dgx
#SBATCH --qos=freetier
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=2-00:00:00
#SBATCH --signal=B:TERM@60
#SBATCH --output=/network/rit/lab/islam_lab/mishu/sigprofiler_webapp/logs/workbench-%j.log
#
# freetier allows up to 7-00:00:00 but is preemptible by paidtier-1 jobs.
# paidtier-1 is not preempted but caps --time at 1-00:00:00.

set -euo pipefail

WORK_ROOT=/network/rit/lab/islam_lab/mishu/sigprofiler_webapp
REPO="${WORK_ROOT}/SigProfilerExtractor"
PY="${REPO}/.venv-dashboard/bin/python"
ENDPOINT_FILE="${WORK_ROOT}/workbench_endpoint.env"
CLUSTER_DOMAIN=its.albany.edu

# Everything on lab storage, not the small $HOME:
#   results     -> $WORK_ROOT/SigProfilerExtractor_results (the Workbench default)
#   uploads     -> $WORK_ROOT/uploads
#   run records -> $WORK_ROOT/.cache/sigprofilerextractor
#   genomes     -> inside the venv, when installed from the Genome card
export HOME="${WORK_ROOT}"
export XDG_CACHE_HOME="${WORK_ROOT}/.cache"
export MPLCONFIGDIR="${WORK_ROOT}/.cache/matplotlib"
export UV_CACHE_DIR="${WORK_ROOT}/.cache/uv"
# os.cpu_count() reports the whole node (256), not this job's CPUs, and
# SigProfilerExtractor's default cpu=-1 means "all of them". Python 3.13+
# reads this variable instead, so runs use exactly the allocation.
export PYTHON_CPU_COUNT="${SLURM_CPUS_PER_TASK:-8}"
mkdir -p "${WORK_ROOT}/uploads" "${WORK_ROOT}/SigProfilerExtractor_results" "${MPLCONFIGDIR}"

if [[ ! -x "${PY}" ]]; then
    echo "FATAL: ${PY} missing -- set up the venv first (see README.md)" >&2
    exit 1
fi

NODE="${SLURMD_NODENAME:-$(hostname -s)}"
FQDN="${NODE}.${CLUSTER_DOMAIN}"

# One Workbench job at a time. Run records live in one shared folder, and the
# Workbench judges a run alive by its process ID on its own node: a second job
# elsewhere would mark this one's runs as failed, and its Quit could signal an
# unrelated process that happens to reuse the ID.
OTHERS=$(squeue -h -u "${USER}" -n spe_workbench -t RUNNING,COMPLETING -o '%i on %N' \
         | awk -v me="${SLURM_JOB_ID:-}" '$1 != me' | paste -sd ' ')
if [[ -n "${OTHERS}" ]]; then
    echo "FATAL: a Workbench job is already running (${OTHERS})." >&2
    echo "       Use it (cat ${ENDPOINT_FILE}), or scancel it before starting another." >&2
    exit 1
fi

# Random port, retried until free (other users' jobs may share the node).
for _ in $(seq 50); do
    PORT=$(shuf -i 20000-60000 -n 1)
    (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null || break
done

# Fresh token per job, handed over in the environment (argv is visible to
# every user on the node through ps). The port is open to the campus network
# and the Workbench reads your files and runs processes as you.
export SPE_GATEWAY_TOKEN=$("${PY}" -c 'import secrets; print(secrets.token_hex(24))')
URL="http://${FQDN}:${PORT}/?token=${SPE_GATEWAY_TOKEN}"

umask 077
cat > "${ENDPOINT_FILE}" <<EOF
# Written by run_workbench.sbatch -- current Workbench location.
WORKBENCH_URL=${URL}
TOKEN=${SPE_GATEWAY_TOKEN}
JOB_ID=${SLURM_JOB_ID:-manual}
NODE=${NODE}
PORT=${PORT}
UPDATED=$(date -Is)
EOF

echo "=== SigProfilerExtractor Workbench, job ${SLURM_JOB_ID:-manual} on ${NODE} ==="
echo "GPU(s): ${CUDA_VISIBLE_DEVICES:-none}   CPUs: ${SLURM_CPUS_PER_TASK:-?}"
echo
echo "Open (campus network or VPN):"
echo "  ${URL}"
echo
echo "Off campus without VPN, tunnel first (same port on both ends), then open"
echo "  http://localhost:${PORT}/?token=${SPE_GATEWAY_TOKEN}"
echo "  ssh -N -L ${PORT}:${FQDN}:${PORT} ${USER}@dgx-head01.${CLUSTER_DOMAIN}"
echo
echo "Stop with Quit in the Workbench, or:  scancel ${SLURM_JOB_ID:-<jobid>}"
echo

exec "${PY}" "${WORK_ROOT}/gateway/spe_gateway.py" \
    --port "${PORT}" \
    --public-host "${FQDN}" \
    --uploads "${WORK_ROOT}/uploads"
