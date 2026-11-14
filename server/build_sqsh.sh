#!/bin/bash
#
# build_sqsh.sh -- build the Workbench image for this cluster, as an enroot
# squashfs on lab storage, from the same recipe as the Dockerfile
# (gateway/install.sh). Docker cannot be used here; enroot runs the result
# (run_workbench.sbatch).
#
#   sbatch build_sqsh.sh            # or run it inside any job: ./build_sqsh.sh
#   SPE_REF=v1.6.2 sbatch build_sqsh.sh
#
# Rebuild after changing gateway/ or to update SigProfilerExtractor. The new
# image is used by the next run_workbench.sbatch job. About 10 minutes.
#
#SBATCH --job-name=spe_build
#SBATCH --partition=dgx
#SBATCH --qos=freetier
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=/network/rit/lab/islam_lab/mishu/sigprofiler_webapp/logs/build-%j.log

set -euo pipefail

WORK_ROOT=/network/rit/lab/islam_lab/mishu/sigprofiler_webapp
OUT="${WORK_ROOT}/images/spe-workbench.sqsh"
BASE="docker://python:3.13-slim"
# Keep in step with the Dockerfile's ARGs.
export SPE_REF="${SPE_REF:-b7cd956c119d8d12d9ead98c6f11a38e11e7aeab}"
export TORCH="${TORCH:-cu128}"

# enroot unpacks images in its temp and data folders: node-local disk, not NFS.
SCRATCH="/raid/${USER}/spe-build-$$"
mkdir -p "${SCRATCH}" 2>/dev/null || SCRATCH="${WORK_ROOT}/.enroot-build-$$"
mkdir -p "${SCRATCH}/tmp" "${SCRATCH}/data" "$(dirname "${OUT}")"
export ENROOT_TEMP_PATH="${SCRATCH}/tmp" ENROOT_DATA_PATH="${SCRATCH}/data"
NAME="spe-build-$$"
trap 'enroot remove -f "${NAME}" >/dev/null 2>&1 || true; rm -rf "${SCRATCH}"' EXIT

echo "[$(date -Is)] base image ${BASE}"
enroot import -o "${SCRATCH}/base.sqsh" "${BASE}"
enroot create -n "${NAME}" "${SCRATCH}/base.sqsh"

echo "[$(date -Is)] installing (SPE_REF=${SPE_REF}, TORCH=${TORCH})"
enroot start --root --rw -m "${WORK_ROOT}/gateway:/src" -e SPE_REF -e TORCH "${NAME}" sh -c '
    set -eu
    sh /src/install.sh
    rm -rf /opt/spe-workbench && mkdir -p /opt/spe-workbench
    cp -r /src/. /opt/spe-workbench/
    find /opt/spe-workbench -name __pycache__ -prune -exec rm -rf {} +
    chmod 755 /opt/spe-workbench/entrypoint.sh /opt/spe-workbench/spe-workbench
    printf "built %s\nSPE_REF %s\nTORCH %s\n" "$(date -Is)" "$SPE_REF" "$TORCH" > /opt/spe-workbench/BUILD_INFO
    # The Dockerfile'"'"'s ENV, for enroot: the NVIDIA pair makes its GPU hook add
    # the driver and nvidia-smi (without them the GPU stays invisible).
    printf "%s\n" PYTHONUNBUFFERED=1 NVIDIA_VISIBLE_DEVICES=all \
        NVIDIA_DRIVER_CAPABILITIES=compute,utility >> /etc/environment
'

echo "[$(date -Is)] exporting ${OUT}"
rm -f "${OUT}.partial"
enroot export -o "${OUT}.partial" "${NAME}"
mv -f "${OUT}.partial" "${OUT}"
ls -lh "${OUT}"
echo "[$(date -Is)] done"
