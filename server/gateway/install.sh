#!/bin/sh
#
# Installs what the Workbench image needs, on a python:3.13-slim base, as root.
# The one recipe for both images: ../Dockerfile runs it, and so does
# ../build_sqsh.sh for the cluster's enroot image.
#
#   SPE_REF  SigProfilerExtractor commit, tag or branch to install
#   TORCH    PyTorch build: cu128 (NVIDIA driver 525+, also runs on CPU) or cpu
#
set -eux

: "${SPE_REF:?set SPE_REF}"
: "${TORCH:=cu128}"

# git: pip installs SigProfilerExtractor from its repository, and its version
# number comes from the git history.
apt-get update
apt-get install -y --no-install-recommends git
rm -rf /var/lib/apt/lists/*

# PyTorch first, from its own index, so SigProfilerExtractor keeps this build.
pip install --no-cache-dir torch --index-url "https://download.pytorch.org/whl/${TORCH}"
pip install --no-cache-dir "git+https://github.com/SigProfilerSuite/SigProfilerExtractor.git@${SPE_REF}"

python3 -c "import SigProfilerExtractor, torch; print('SigProfilerExtractor', SigProfilerExtractor.__version__, 'torch', torch.__version__)"
