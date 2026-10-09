#!/usr/bin/env bash
# Download CMU's chess app checkout at the task's immutable base commit.
set -euo pipefail
cd "$(dirname "$0")/.."
source_url="https://github.com/cmu-agents/chess-app.git"
revision="$(python -c 'import json; print(json.load(open("tasks/chess-terminal-move/task.json"))["base_commit"])')"
if [[ -d chess_app/.git || -f chess_app/.git ]]; then
  echo "chess_app checkout already exists; verify-sources checks its exact revision"
  exit 0
fi
if [[ -e chess_app ]]; then
  echo "ERROR: chess_app exists but is not a git checkout" >&2
  exit 1
fi
# Read-only checkout; GitHub authentication is not required for this public repo.
git clone --filter=blob:none "$source_url" chess_app
git -C chess_app checkout --detach "$revision"
echo "Fetched chess_app at ${revision:0:12}"
