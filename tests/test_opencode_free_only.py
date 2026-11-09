"""Offline checks that a free-only OpenCode run can never use a paid API key."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from assignment.opencode_runner import (
    DEFAULT_FREE_MODEL, OPENCODE_BINARY, OpenCodeRunError, OpenCodeRunner,
    classify_run_output, credential_like_names, is_free_opencode_model,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_run_opencode():
    spec = importlib.util.spec_from_file_location("run_opencode", ROOT / "scripts/run_opencode.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SandboxStub:
    """Pretends to be the Docker sandbox; records what each command would see."""

    cwd = "/testbed"

    def __init__(self, *, container_env="PATH=/usr/bin\nHOME=/root\n", agent_exit=0,
                 agent_output='{"type":"step_finish"}\n', changed=("src/fix.py",)):
        self.calls = []
        self.container_env = container_env
        self.agent_exit = agent_exit
        self.agent_output = agent_output
        self.changed = list(changed)

    def execute(self, command, *, shell=False, cwd=None, env=None, timeout=None):
        self.calls.append({"command": command, "cwd": cwd, "env": env})
        out, code = "", 0
        if command == ["env"]:
            out = self.container_env + "".join(f"{k}={v}\n" for k, v in (env or {}).items())
        elif command[:2] == ["git", "status"]:
            out = ""
        elif command[:3] == ["git", "diff", "--name-only"]:
            out = "\0".join(self.changed) + ("\0" if self.changed else "")
        elif command[:3] == ["git", "ls-files", "--others"]:
            out = ""
        elif command[:3] == ["git", "diff", "--binary"]:
            out = "diff --git a/src/fix.py b/src/fix.py\n+fix\n"
        elif command[0] == OPENCODE_BINARY and "run" in command:
            out, code = self.agent_output, self.agent_exit
        elif command[0] == OPENCODE_BINARY:
            out = "1.19.2\n"
        return {"returncode": code, "stdout": out, "stderr": "", "output": out}


def test_free_model_pattern():
    assert is_free_opencode_model(DEFAULT_FREE_MODEL)
    assert is_free_opencode_model("opencode/mimo-v2.6-flash-free")
    for paid in ("openai/gpt-5-mini", "deepseek/deepseek-flash", "opencode/deepseek-v4.1-flash",
                 "opencode/x-free/extra", "OPENCODE/x-free", "", "opencode/-free"):
        assert not is_free_opencode_model(paid), paid


def test_free_only_rejects_paid_models_and_any_credentials():
    with pytest.raises(ValueError, match="free models"):
        OpenCodeRunner(SandboxStub(), model="openai/gpt-5-mini", free_only=True)
    with pytest.raises(ValueError, match="must not receive any credentials"):
        OpenCodeRunner(SandboxStub(), model=DEFAULT_FREE_MODEL, free_only=True,
                       credential_env={"OPENAI_API_KEY": "FAKE"})


def test_free_only_run_passes_no_env_and_checks_the_sandbox_first():
    env = SandboxStub()
    result = OpenCodeRunner(env, model=DEFAULT_FREE_MODEL, free_only=True).run("Fix it")
    assert result.patch.startswith("diff --git")
    commands = [c["command"] for c in env.calls]
    env_check = commands.index(["env"])
    agent_run = next(i for i, c in enumerate(commands) if c[0] == OPENCODE_BINARY and "run" in c)
    assert env_check < agent_run, "credential check must happen before the agent starts"
    assert env.calls[agent_run]["env"] == {}


def test_free_only_refuses_when_container_exposes_a_key():
    env = SandboxStub(container_env="PATH=/usr/bin\nOPENAI_API_KEY=sk-leaked\n")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenCodeRunner(env, model=DEFAULT_FREE_MODEL, free_only=True).run("Fix it")
    assert not any(c["command"][0] == OPENCODE_BINARY and "run" in c["command"] for c in env.calls)


def test_credential_name_detection():
    names = ["PATH", "HOME", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GITHUB_TOKEN",
             "AWS_SECRET_ACCESS_KEY", "ZAI_APIKEY", "OPENAI_BASE_URL", "GPG_KEY"]
    assert credential_like_names(names) == [
        "AWS_SECRET_ACCESS_KEY", "DEEPSEEK_API_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY", "ZAI_APIKEY",
    ]


def test_failed_run_keeps_output_and_classifies_quota():
    env = SandboxStub(agent_exit=124, agent_output="AI_APICallError: Free usage limit reached.\n")
    with pytest.raises(OpenCodeRunError) as caught:
        OpenCodeRunner(env, model=DEFAULT_FREE_MODEL, free_only=True).run("Fix it")
    assert caught.value.status == "quota_limited"
    assert "Free usage limit" in caught.value.output
    assert isinstance(caught.value, RuntimeError)  # existing callers still catch it


def test_clean_exit_without_changes_is_no_patch():
    env = SandboxStub(changed=())
    with pytest.raises(OpenCodeRunError) as caught:
        OpenCodeRunner(env, model=DEFAULT_FREE_MODEL, free_only=True).run("Fix it")
    assert caught.value.status == "no_patch"


@pytest.mark.parametrize("output,code,expected", [
    ("READY", 0, "ok"),
    ("", 124, "timeout"),
    ("boom", 1, "error"),
    ("Free usage limit reached", 0, "quota_limited"),
])
def test_classify_run_output(output, code, expected):
    assert classify_run_output(output, code) == expected


def test_probe_reports_ready_and_quota():
    ok = OpenCodeRunner(SandboxStub(agent_output='{"text":"READY"}\n'),
                        model=DEFAULT_FREE_MODEL, free_only=True).probe()
    assert ok["status"] == "ok"
    limited = OpenCodeRunner(SandboxStub(agent_exit=1, agent_output="Free usage limit reached"),
                             model=DEFAULT_FREE_MODEL, free_only=True).probe()
    assert limited["status"] == "quota_limited"


def test_cli_never_forwards_credentials_for_free_models(monkeypatch):
    module = _load_run_opencode()
    monkeypatch.setenv("OPENAI_API_KEY", "FAKE_OPENAI")
    monkeypatch.setenv("OPENCODE_API_KEY", "FAKE_OPENCODE")
    assert module.select_credentials(DEFAULT_FREE_MODEL, allow_paid=False) == {}
    assert module.select_credentials(DEFAULT_FREE_MODEL, allow_paid=True) == {}
    with pytest.raises(SystemExit, match="allow-paid-model"):
        module.select_credentials("openai/gpt-5-mini", allow_paid=False)
    assert module.select_credentials("openai/gpt-5-mini", allow_paid=True)["OPENAI_API_KEY"] == "FAKE_OPENAI"
