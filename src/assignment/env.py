"""Docker execution adapter for the CMU agent and evaluation harness.

The implementation lives in the independent agent-sandbox-runtime repository.
Only the assignment-specific conda activation and compatibility contract live
here, making the backend replaceable without touching the agent logic.
"""
from __future__ import annotations

import posixpath
from pathlib import PurePath

from agent_sandbox_runtime import DockerImage, Sandbox


class Environment:
    """Synchronous command execution inside a disposable Docker sandbox."""

    def __init__(
        self,
        image: str | PurePath | DockerImage = "python:3.12-slim",
        cwd: str = "/",
        startup_timeout: float = 600,
        runtime_timeout: float = 600,
        deployment_timeout: float = 1800,
        ports: tuple[int, ...] | list[int] = (),
        conda_env: str | None = None,
    ):
        self.cwd = cwd
        self.env_defaults: dict[str, str] = {}
        # Preserve Environment.deployment for callers that introspect this
        # object's lifecycle without exposing Docker implementation internals.
        self.deployment = Sandbox(
            image=image,
            cwd=cwd,
            ports=ports,
            runtime_timeout=runtime_timeout,
            deployment_timeout=deployment_timeout,
        )
        try:
            if conda_env:
                self.activate_conda_env(conda_env)
            info = self.execute("uname -s; uname -r; uname -v; uname -m")
            if info["returncode"] != 0 or len(info["output"].splitlines()) != 4:
                raise RuntimeError(f"Could not inspect sandbox platform: {info['output']}")
            self.system, self.release, self.version, self.machine = info["output"].splitlines()
        except BaseException:
            self.stop()
            raise

    def is_alive(self) -> bool:
        return self.deployment.is_alive()

    def activate_conda_env(self, name: str, root: str = "/opt/miniconda3") -> str:
        if not name or "/" in name or name in {".", ".."}:
            raise ValueError("Conda environment name must be a simple name")
        binary_dir = posixpath.join(root, "envs", name, "bin")
        if self.execute(["test", "-d", binary_dir], cwd="/", shell=False)["returncode"] != 0:
            raise FileNotFoundError(f"No conda environment at {binary_dir}")
        current = self.execute("printenv PATH", cwd="/")["output"].strip()
        self.env_defaults["PATH"] = f"{binary_dir}:{current}"
        return self.env_defaults["PATH"]

    def execute(
        self,
        command: str | list[str],
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        shell: bool | None = True,
        check: bool = False,
    ) -> dict:
        try:
            return self.deployment.execute(
                command,
                timeout=timeout,
                cwd=cwd or self.cwd,
                env={**self.env_defaults, **(env or {})},
                shell=shell,
                check=check,
            )
        except Exception as exc:
            if not self.is_alive():
                raise RuntimeError(f"Sandbox is no longer running: {exc}") from exc
            return {
                "stdout": "",
                "stderr": str(exc),
                "output": str(exc),
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {exc}",
                "extra": {"exception_type": type(exc).__name__, "exception": str(exc)},
            }

    def tunnel_url(self, port: int) -> str:
        """Return the loopback-only mapping for a container TCP port."""
        return self.deployment.tunnel_url(port)

    def stop(self, timeout: float = 10) -> None:
        self.deployment.stop(timeout=timeout)

    def __enter__(self) -> "Environment":
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
