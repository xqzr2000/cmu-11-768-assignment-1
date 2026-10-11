"""Single subprocess boundary for Docker CLI, kept mockable for offline tests."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence


class DockerError(RuntimeError):
    """Docker operation failed with an actionable error."""


def docker(*args: str, timeout: float | None = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    if shutil.which("docker") is None:
        raise DockerError("Docker CLI is not installed. Open the devcontainer or install Docker Desktop.")
    try:
        result = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise DockerError(f"Docker command timed out after {timeout}s: {args[0] if args else ''}") from exc
    except OSError as exc:
        raise DockerError(f"Could not start Docker: {exc}") from exc
    if check and result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise DockerError(f"docker {args[0] if args else ''} failed ({result.returncode}): {details[-3000:]}")
    return result


def docker_ready() -> tuple[bool, str]:
    try:
        result = docker("info", "--format", "{{.ServerVersion}}", timeout=15)
        return True, result.stdout.strip()
    except DockerError as exc:
        return False, str(exc)
