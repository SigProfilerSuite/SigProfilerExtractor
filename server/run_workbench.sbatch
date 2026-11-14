#!/bin/bash
#
# run_workbench.sbatch -- the SigProfilerExtractor Workbench on a DGX node,
# used from the browser on your own computer.
#
#   sbatch run_workbench.sbatch
#   cat workbench_endpoint.env        # URL with token, once the job is running
#   scancel -n spe_workbench          # stop it (or Quit in the Workbench)
#
# Runs the Workbench image (images/spe-workbench.sqsh, built by build_sqsh.sh
# from the same recipe as the Dockerfile) with enroot, the cluster's
# container runtime. Upload inputs, start runs, follow them, explore results
# and download them, all from the browser.
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
IMAGE="${WORK_ROOT}/images/spe-workbench.sqsh"
ENDPOINT_FILE="${WORK_ROOT}/workbench_endpoint.env"
CLUSTER_DOMAIN=its.albany.edu
LOGIN_NODE="dgx-head01.${CLUSTER_DOMAIN}"
# Seen inside the container at the same paths, so any path under them can be
# pasted into the Workbench as it is. Your home folder is mounted as well.
LAB_STORAGE=/network/rit/lab/islam_lab

if [[ ! -s "${IMAGE}" ]]; then
    echo "FATAL: ${IMAGE} missing -- build it first: sbatch ${WORK_ROOT}/build_sqsh.sh" >&2
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

# Fresh token per job. The port is open to the campus network and the
# Workbench reads your files and runs processes as you.
TOKEN=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
URL="http://${FQDN}:${PORT}/?token=${TOKEN}"

umask 077
cat > "${ENDPOINT_FILE}" <<EOF
# Written by run_workbench.sbatch -- current Workbench location.
WORKBENCH_URL=${URL}
TOKEN=${TOKEN}
JOB_ID=${SLURM_JOB_ID:-manual}
NODE=${NODE}
PORT=${PORT}
UPDATED=$(date -Is)
EOF

echo "=== SigProfilerExtractor Workbench, job ${SLURM_JOB_ID:-manual} on ${NODE} ==="
echo "GPU(s): ${CUDA_VISIBLE_DEVICES:-none}   CPUs: ${SLURM_CPUS_PER_TASK:-?}   image: ${IMAGE}"
echo "Stop with Quit in the Workbench, or:  scancel ${SLURM_JOB_ID:-<jobid>}"

# The image's entrypoint prints the link and starts the app. Its data folder
# is this folder, as before: uploads/, SigProfilerExtractor_results/, run
# records in .cache/, genomes in references/. The settings reach it through
# the environment (argv is visible to every user on the node through ps).
export SPE_DATA="${WORK_ROOT}"
export SPE_PORT="${PORT}"
export SPE_TOKEN="${TOKEN}"
export SPE_HOST_NAME="${FQDN}"
export SPE_SSH_USER="${USER}"
export SPE_SSH_VIA="${LOGIN_NODE}"
# os.cpu_count() reports the whole node (256), not this job's CPUs, and
# SigProfilerExtractor's default cpu=-1 means "all of them". Python 3.13+
# reads this variable instead, so runs use exactly the allocation.
export PYTHON_CPU_COUNT="${SLURM_CPUS_PER_TASK:-8}"
export PYTHONUNBUFFERED=1

# exec: scancel and the time limit's TERM reach the app, which stops its runs.
exec srun --ntasks=1 \
    --container-image="${IMAGE}" \
    --container-mounts="${LAB_STORAGE}:${LAB_STORAGE}" \
    --container-writable \
    /opt/spe-workbench/entrypoint.sh
