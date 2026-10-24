FROM python:3.12-slim

# Install system dependencies at image-build time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install OpenCode 1 before applying sandbox restrictions.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN curl -fsSL https://opencode.ai/install \
    | bash -s -- --version 1.19.4 --no-modify-path

ENV PATH="/root/.opencode/bin:${PATH}"

# Copy the pinned chess source into the image.
COPY . /testbed
WORKDIR /testbed

RUN git init -q -b main . \
    && git add -A \
    && git -c user.email=harness@localhost \
       -c user.name=harness \
       commit -q -m "baseline"

RUN pip install --no-cache-dir \
    -e ./packages/agent-sandbox-runtime \
    -e . \
    pytest
