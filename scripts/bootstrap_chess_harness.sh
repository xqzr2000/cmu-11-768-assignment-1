#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

REV="$(python - <<'PY'
import json
from pathlib import Path

spec = json.loads(
    Path("tasks/chess-harness-improvement/task.json").read_text()
)
print(spec["base_commit"])
PY
)"

TARGET=".private/chess-harness-base"

if [[ -e "$TARGET" ]]; then
    echo "Existing chess harness baseline found."
else
    echo "Creating chess harness baseline..."

    git cat-file -e "${REV}^{commit}" || {
        echo "Baseline commit unavailable: $REV" >&2
        exit 1
    }

    mkdir -p .private
    git worktree add --detach "$TARGET" "$REV"
fi

uv run python - <<'PY'
from assignment.task import Task
from assignment.utils.image import verify_source

task = Task.load("tasks/chess-harness-improvement")
verify_source(task)

print("Chess harness baseline verified: PASS")
print("Commit:", task.base_commit)
PY
