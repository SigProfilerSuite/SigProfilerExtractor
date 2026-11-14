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
# panel. Data lives in the mounted folder, never in the image.

FROM python:3.13-slim

# The SigProfilerExtractor commit to install (a tag or branch also works).
ARG SPE_REF=b7cd956c119d8d12d9ead98c6f11a38e11e7aeab
# PyTorch build. cu128 uses an NVIDIA GPU with driver 525 or newer and also
# runs on servers without one; "cpu" makes the image about 4 GB smaller.
ARG TORCH=cu128

# git: pip installs SigProfilerExtractor from its repository, and its version
# number comes from the git history.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

# PyTorch first, from its own index, so SigProfilerExtractor keeps this build.
RUN pip install --no-cache-dir torch --index-url "https://download.pytorch.org/whl/${TORCH}"
RUN pip install --no-cache-dir \
      "git+https://github.com/SigProfilerSuite/SigProfilerExtractor.git@${SPE_REF}"

COPY gateway/ /opt/spe-workbench/
RUN chmod 755 /opt/spe-workbench/entrypoint.sh /opt/spe-workbench/spe-workbench

ENV SPE_DATA=/data \
    SPE_PORT=8765 \
    PYTHONUNBUFFERED=1
EXPOSE 8765
VOLUME /data
ENTRYPOINT ["/opt/spe-workbench/entrypoint.sh"]
