"""Check source, Docker daemon and OpenAI settings without launching an agent."""
from __future__ import annotations

import argparse
import os
from urllib.parse import urlparse

import httpx
from agent_sandbox_runtime.process import docker_ready
from dotenv import load_dotenv

from assignment.task import Task
from assignment.utils.image import SourceMismatch, verify_source


TASKS = ("tasks/chess-terminal-move",)
PLACEHOLDERS = ("replace-", "course-key", "<", ">")


def _configured(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value or any(marker in value.lower() for marker in PLACEHOLDERS):
        return None
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Do not contact the OpenAI endpoint")
    args = parser.parse_args()
    load_dotenv()
    errors = []
    for task_path in TASKS:
        try:
            verify_source(Task.load(task_path))
            print(f"[ok] pinned source: {task_path}")
        except (FileNotFoundError, SourceMismatch, ValueError) as exc:
            errors.append(f"{task_path}: {exc}")
    ready, detail = docker_ready()
    if ready:
        print(f"[ok] Docker daemon: {detail}")
    else:
        errors.append(f"Docker: {detail}")
    api_key = _configured("OPENAI_API_KEY")
    model = _configured("OPENAI_MODEL")
    base_url = _configured("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    if not api_key:
        errors.append("OPENAI_API_KEY is missing")
    else:
        print("[ok] OPENAI_API_KEY configured")
    if not model:
        errors.append("OPENAI_MODEL is missing")
    else:
        print(f"[ok] OPENAI_MODEL: {model}")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("OPENAI_BASE_URL must be a complete HTTPS URL")
    else:
        print(f"[ok] Inference endpoint: {parsed.netloc}")
    if not args.offline and api_key and parsed.scheme == "https":
        try:
            response = httpx.get(
                base_url.rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {api_key}"}, timeout=10,
            )
            if response.status_code in (401, 403):
                errors.append(f"Endpoint rejected the API key ({response.status_code})")
            elif response.status_code >= 500:
                errors.append(f"Endpoint returned {response.status_code}")
            elif response.status_code == 200:
                print("[ok] Model API accepted the credential")
            else:
                print(f"[warning] GET /models returned {response.status_code}")
        except httpx.HTTPError as exc:
            errors.append(f"Could not reach inference endpoint: {exc}")
    for error in errors:
        print(f"[error] {error}")
    print("Ready for Docker sandboxes." if not errors else "Configuration needs attention.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
