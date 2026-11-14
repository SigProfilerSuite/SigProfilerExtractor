# SigProfilerExtractor Workbench, served for use from another computer's browser.
#
# Build (from this folder):
#   docker build -t mishugeb/sigprofilerextractor-workbench .
#   docker build -t mishugeb/sigprofilerextractor-workbench:cpu --build-arg TORCH=cpu .
#
# Run: gateway/spe-workbench start   (or see README.md, "Your own server")
#
# The image holds SigProfilerExtractor (unchanged, from GitHub) and the gateway
# from gateway/: a token sign-in, upload, .zip download and the resources
# panel. Data lives in the mounted folder, never in the image. The cluster's
# enroot image (build_sqsh.sh) is built by the same gateway/install.sh.

FROM python:3.13-slim

# The SigProfilerExtractor commit to install (a tag or branch also works).
ARG SPE_REF=b7cd956c119d8d12d9ead98c6f11a38e11e7aeab
# PyTorch build. cu128 uses an NVIDIA GPU with driver 525 or newer and also
# runs on servers without one; "cpu" makes the image about 4 GB smaller.
ARG TORCH=cu128

# Installed before the rest of gateway/ is copied, so editing the gateway
# does not reinstall PyTorch.
COPY gateway/install.sh /tmp/install.sh
RUN SPE_REF="${SPE_REF}" TORCH="${TORCH}" sh /tmp/install.sh && rm /tmp/install.sh

COPY gateway/ /opt/spe-workbench/
RUN chmod 755 /opt/spe-workbench/entrypoint.sh /opt/spe-workbench/spe-workbench

# The NVIDIA settings ask the container runtime (Docker's NVIDIA toolkit,
# enroot, Apptainer --nv) to add the GPU driver and nvidia-smi; NVIDIA's own
# CUDA images set the same. Without them the GPU stays invisible.
ENV SPE_DATA=/data \
    SPE_PORT=8765 \
    PYTHONUNBUFFERED=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility
EXPOSE 8765
VOLUME /data
ENTRYPOINT ["/opt/spe-workbench/entrypoint.sh"]
