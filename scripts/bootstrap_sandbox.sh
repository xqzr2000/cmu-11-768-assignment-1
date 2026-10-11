#!/usr/bin/env bash
# Backward-compatible no-op: Docker runtime is vendored under packages/.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f packages/agent-sandbox-runtime/pyproject.toml ]]; then
  echo 'ERROR: Missing packages/agent-sandbox-runtime; upload the complete repository.' >&2
  exit 1
fi
echo 'Sandbox runtime is bundled in packages/agent-sandbox-runtime; no clone necessary.'
