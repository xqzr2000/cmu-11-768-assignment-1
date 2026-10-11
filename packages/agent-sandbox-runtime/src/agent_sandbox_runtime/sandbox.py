"""Disposable Docker-backed shell environment and private local port access."""

from __future__ import annotations

import math
import re
import shlex
import time
import uuid
from pathlib import Path
from typing import Mapping

from .image import DockerImage
from .process import DockerError, docker

PORT_PATTERN = re.compile(r"^127\.0\.0\.1:(\d+)$")


class SandboxError(DockerError):
    """Sandbox cannot be started or reached."""


class Sandbox:
    """One isolated Docker container (not a hardened VM security boundary).

    The container runs only for a bounded time, uses no host mounts or Docker
    socket, drops privileges, and publishes specified ports on loopback only.
    Shell commands are run via docker exec. No OpenAI credentials are passed in.
    """

    def __init__(
        self,
        image: str | Path | DockerImage = "python:3.12-slim",
        *,
        cwd: str = "/",
        ports: tuple[int, ...] | list[int] = (),
        deployment_timeout: float = 1800,
        runtime_timeout: float = 600,
        cpus: float = 2.0,
        memory: str = "4g",
        network: str = "bridge",
    ) -> None:
        if not 1 <= deployment_timeout <= 86400:
            raise ValueError("deployment_timeout must be between 1 and 86400 seconds")
        if not 0 < cpus <= 128:
            raise ValueError("Invalid CPU limit")
        if any(not isinstance(p, int) or not 1 <= p <= 65535 for p in ports):
            raise ValueError("Port numbers must be between 1 and 65535")
        if network not in ("bridge", "none"):
            raise ValueError("Only 'bridge' or 'none' networking is supported")
        self.cwd = cwd
        self.runtime_timeout = runtime_timeout
        self.started = time.monotonic()
        self.deployment_timeout = deployment_timeout
        self.ports = tuple(dict.fromkeys(ports))
        self.name = "agent-sbx-" + uuid.uuid4().hex[:12]
        self.id = ""
        image_name = image.build() if isinstance(image, DockerImage) else str(image)
        if not image_name or isinstance(image, Path) and image.is_file():
            raise ValueError("Sandbox image must be a Docker image name or DockerImage recipe")
        argv = [
            "run", "--detach", "--rm", "--name", self.name,
            "--label", "org.agent-sandbox-runtime.managed=true",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", "256", "--memory", memory, "--cpus", str(cpus),
            "--network", network, "--workdir", cwd,
        ]
        for port in self.ports:
            argv.extend(["--publish", f"127.0.0.1::{port}"])
        # Sleeping as PID 1 makes the lifetime an independent engine-enforced
        # upper bound: a dead agent process cannot leave a billable container.
        argv += ["--entrypoint", "/bin/sh", image_name, "-c", f"exec sleep {math.ceil(deployment_timeout)}"]
        try:
            self.id = docker(*argv, timeout=1800).stdout.strip()
            if not self.id:
                raise SandboxError("Docker did not return a container ID")
            self.started = time.monotonic()
        except BaseException:
            # A failed start must not leave a half-created named container.
            try:
                docker("rm", "--force", self.name, check=False, timeout=30)
            except DockerError:
                pass
            raise

    def is_alive(self) -> bool:
        if not self.id:
            return False
        if time.monotonic() - self.started > self.deployment_timeout:
            self.stop()
            return False
        try:
            return docker("inspect", "--format", "{{.State.Running}}", self.id, check=False, timeout=10).stdout.strip() == "true"
        except DockerError:
            return False

    def execute(
        self,
        command: str | list[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        shell: bool | None = True,
        check: bool = False,
    ) -> dict:
        if not self.is_alive():
            raise SandboxError("Sandbox is no longer running")
        effective_timeout = self.runtime_timeout if timeout is None else timeout
        if effective_timeout is not None and effective_timeout <= 0:
            raise ValueError("timeout must be positive")
        argv = ["exec", "--workdir", cwd or self.cwd]
        for key, value in (env or {}).items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError(f"Invalid environment variable name: {key}")
            argv += ["--env", f"{key}={value}"]
        argv.append(self.id)
        if shell is None:
            shell = True
        if shell:
            script = command if isinstance(command, str) else shlex.join(command)
            command_argv = ["/bin/bash", "-c", script]
        else:
            if not isinstance(command, (list, tuple)) or not command:
                raise ValueError("shell=False requires a nonempty argv list")
            command_argv = list(command)
        # GNU timeout enforces command lifetime inside the container; the
        # subprocess's own timeout is a final guard for a stuck Docker client.
        if effective_timeout is not None:
            command_argv = ["timeout", "--signal=TERM", "--kill-after=2", str(math.ceil(effective_timeout)), *command_argv]
        result = docker(*argv, *command_argv, timeout=(effective_timeout + 15 if effective_timeout else 1800), check=False)
        output = {
            "stdout": result.stdout, "stderr": result.stderr,
            "output": result.stdout + result.stderr, "returncode": result.returncode,
            "exception_info": "",
        }
        if check and result.returncode != 0:
            raise SandboxError(f"Command exited {result.returncode}: {output['output'][-2000:]}")
        if result.returncode == 124:
            output["exception_info"] = f"Command timed out after {effective_timeout}s"
        return output

    def tunnel_url(self, port: int) -> str:
        """Private loopback URL for a published container TCP port."""
        if port not in self.ports:
            raise ValueError(f"Port {port} was not exposed; exposed ports: {self.ports}")
        result = docker("port", self.id, f"{port}/tcp", timeout=10).stdout.strip()
        for line in result.splitlines():
            match = PORT_PATTERN.fullmatch(line)
            if match:
                return f"http://127.0.0.1:{match.group(1)}"
        raise SandboxError(f"Expected loopback-only Docker port mapping, got: {result!r}")

    def stop(self, timeout: float = 10) -> None:
        if self.id:
            container_id, self.id = self.id, ""
            docker("rm", "--force", container_id, timeout=timeout + 5, check=False)

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
