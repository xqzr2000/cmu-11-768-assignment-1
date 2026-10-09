#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
git config --global --add safe.directory "$PWD" || true
git config --global --add safe.directory "$PWD/chess_app" || true
make setup
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created ignored .env file. Codespaces secrets also work directly."
fi
printf '\nSetup complete. Run make sandbox-doctor, make doctor, make test, then make test-docker.\n'
