#!/usr/bin/env bash
# Keep the runtime independent: an editable sibling checkout is a UV source.
set -euo pipefail
cd "$(dirname "$0")/.."
RUNTIME_DIR="$(realpath -m ../russells-agent-sandbox)"
if [[ -f "$RUNTIME_DIR/pyproject.toml" ]] && grep -q 'name = "agent-sandbox-runtime"' "$RUNTIME_DIR/pyproject.toml"; then
  echo "Using sibling sandbox checkout: $RUNTIME_DIR"
  exit 0
fi
if [[ -e "$RUNTIME_DIR" ]]; then
  echo "ERROR: $RUNTIME_DIR already exists but is not the sandbox runtime repo" >&2
  exit 1
fi
# User may explicitly supply the target repository URL. Otherwise infer a
# sibling repo belonging to the same GitHub user/org as this repository.
url="${SANDBOX_RUNTIME_GIT_URL:-}"
if [[ -z "$url" ]]; then
  parent="${GITHUB_REPOSITORY:-}"
  if [[ -z "$parent" ]]; then
    origin="$(git remote get-url origin 2>/dev/null || true)"
    if [[ "$origin" =~ ^https://([^/@]+@)?github.com/([^/]+)/ ]]; then
      parent="${BASH_REMATCH[2]}/cmu-11-768-assignment-1"
    elif [[ "$origin" =~ ^git@github.com:([^/]+)/ ]]; then
      parent="${BASH_REMATCH[1]}/cmu-11-768-assignment-1"
    fi
  fi
  if [[ -n "$parent" ]]; then
    owner="${parent%%/*}"
    url="https://github.com/$owner/russells-agent-sandbox.git"
  fi
fi
if [[ -z "$url" ]]; then
  echo "ERROR: clone russells-agent-sandbox beside cmu-11-768-assignment-1, or set SANDBOX_RUNTIME_GIT_URL." >&2
  exit 1
fi
echo "Cloning independent sandbox runtime: $url"
git clone --depth 1 --branch "${SANDBOX_RUNTIME_REF:-v0.1.0}" "$url" "$RUNTIME_DIR"
