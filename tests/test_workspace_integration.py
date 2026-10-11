"""Offline regression checks: the bundled runtime really is in this repo."""
from pathlib import Path
from importlib import import_module


def test_bundled_runtime_metadata():
    root = Path(__file__).resolve().parents[1]
    package = root / "packages" / "agent-sandbox-runtime"
    assert (package / "pyproject.toml").is_file()
    assert (package / "src" / "agent_sandbox_runtime" / "sandbox.py").is_file()
    assert (package / "LICENSE").is_file()
    from agent_sandbox_runtime import Sandbox, DockerImage
    assert Sandbox is not None and DockerImage is not None


def test_workspace_dependency_configuration():
    import tomllib
    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as f:
        config = tomllib.load(f)
    assert config["tool"]["uv"]["sources"]["agent-sandbox-runtime"] == {"workspace": True}
    assert "packages/agent-sandbox-runtime" in config["tool"]["uv"]["workspace"]["members"]
