FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

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
