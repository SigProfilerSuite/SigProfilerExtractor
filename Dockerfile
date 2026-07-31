# CUDA-enabled base image for GPU support
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG COMMIT_SHA=master

# Install Python + minimal deps
RUN apt-get update && apt-get install -y \
    python3-pip python3-dev git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Upgrade Ubuntu's packaging tools before invoking the PEP 517 build backend.
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /usr/src/app

# Install GPU-enabled PyTorch wheels
RUN pip3 install --no-cache-dir \
    torch torchvision torchaudio \
    --extra-index-url https://download.pytorch.org/whl/cu118

# Install SigProfilerExtractor from specific commit
RUN pip3 install --no-cache-dir \
    'git+https://github.com/SigProfilerSuite/SigProfilerExtractor.git@'${COMMIT_SHA}

# Create a non-root user
RUN useradd -m -s /bin/bash spm_user
RUN chown -R spm_user:spm_user /usr/src/app
USER spm_user
