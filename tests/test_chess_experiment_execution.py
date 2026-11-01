"""Offline regression tests for one chess experiment trial."""

import json
from pathlib import Path
from runpy import run_path

import pytest

from assignment.agent.base import StepLimitError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_chess_experiment.py"
execute_trial = run_path(str(SCRIPT))["execute_trial"]


def make_plan(**changes):
    plan = {
        "dry_run": False,
        "working_tree_clean": True,
        "environment": "original chess application, no patch",
        "patch_sha256": None,
        "model": "gpt-5-mini",
        "step_limit": 3,
        "chess_agent": {
            "programmatic_tools": False,
            "include_legal_moves": True,
            "skills_path": None,
        },
    }
    plan.update(changes)
    return plan


def make_trial(tmp_path):
    directory = tmp_path / "experiment"
    return {
        "trial_id": "trial-001",
        "trajectory": str(directory / "trajectory.json"),
        "result": str(directory / "result.json"),
        "report": str(directory / "report.json"),
    }


def status_file(trial):
    return Path(trial["report"]).with_name("trial-001-status.json")


def fake_dependencies(events, mode="completed", save_trajectory=True):
    class FakeSandbox:
        def __enter__(self):
            events.append("sandbox_enter")
            return self

        def __exit__(self, *args):
            events.append("sandbox_exit")

    def sandbox_factory(**kwargs):
        events.append(("sandbox_config", kwargs))
        return FakeSandbox()

    class FakeAgent:
        def __init__(self, **kwargs):
            events.append(("agent_config", kwargs))
            self.path = Path(kwargs["logs_save_path"])
            self.steps_taken = 3
            self.finished = mode == "completed"
            self.last_state = {
                "game_over": self.finished,
                "fen": "test-position",
            }

        def run(self):
            events.append("agent_run")

            if save_trajectory:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps({
                    "prompts": [],
                    "responses": [],
                    "compactions": [],
                }))

            if mode == "step_limit":
                raise StepLimitError("Simulated step limit")

            if mode == "failure":
                raise RuntimeError("Simulated agent failure")

    def agent_factory(**kwargs):
        return FakeAgent(**kwargs)

    def observation_recorder(path, agent):
        events.append("observations_recorded")

    def evaluator(trajectory, result):
        events.append("evaluation_run")

        assert json.loads(Path(trajectory).read_text())["responses"] == []
        state = json.loads(Path(result).read_text())

        return {
            "model_steps": 3,
            "game_over": state["game_over"],
        }

    return {
        "sandbox_factory": sandbox_factory,
        "agent_factory": agent_factory,
        "observation_recorder": observation_recorder,
        "evaluator": evaluator,
    }


def test_completed_trial(tmp_path):
    events = []
    trial = make_trial(tmp_path)

    status = execute_trial(
        make_plan(), trial, **fake_dependencies(events)
    )

    assert status["outcome"] == "completed"
    assert status["report_written"] is True
    assert status["game_over"] is True
    assert status["error"] is None

    assert json.loads(Path(trial["result"]).read_text())["game_over"]
    assert json.loads(Path(trial["report"]).read_text())["model_steps"] == 3
    assert json.loads(status_file(trial).read_text()) == status

    agent_kwargs = next(
        item[1] for item in events
        if isinstance(item, tuple) and item[0] == "agent_config"
    )
    assert agent_kwargs["model"] == "gpt-5-mini"
    assert agent_kwargs["auto_stop_environment"] is False
    assert "sandbox_exit" in events
    assert "evaluation_run" in events


def test_step_limit_still_produces_report(tmp_path):
    events = []
    trial = make_trial(tmp_path)

    status = execute_trial(
        make_plan(),
        trial,
        **fake_dependencies(events, mode="step_limit"),
    )

    assert status["outcome"] == "step_limit"
    assert status["model_steps"] == 3
    assert status["game_over"] is False
    assert status["report_written"] is True
    assert Path(trial["report"]).exists()
    assert "sandbox_exit" in events


def test_agent_failure_preserves_diagnostics(tmp_path):
    events = []
    trial = make_trial(tmp_path)

    status = execute_trial(
        make_plan(),
        trial,
        **fake_dependencies(events, mode="failure"),
    )

    assert status["outcome"] == "failed"
    assert "Simulated agent failure" in status["error"]
    assert status["report_written"] is False
    assert Path(trial["trajectory"]).exists()
    assert json.loads(Path(trial["result"]).read_text())
    assert not Path(trial["report"]).exists()
    assert "sandbox_exit" in events


def test_missing_trajectory_is_failure(tmp_path):
    events = []
    trial = make_trial(tmp_path)

    status = execute_trial(
        make_plan(),
        trial,
        **fake_dependencies(events, save_trajectory=False),
    )

    assert status["outcome"] == "failed"
    assert "Trajectory was not saved" in status["error"]
    assert status["report_written"] is False
    assert "sandbox_exit" in events


@pytest.mark.parametrize(
    "output_name",
    ["trajectory", "result", "report", "status"],
)
def test_refuses_to_overwrite(tmp_path, output_name):
    events = []
    trial = make_trial(tmp_path)

    path = (
        status_file(trial)
        if output_name == "status"
        else Path(trial[output_name])
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("DO NOT OVERWRITE")

    with pytest.raises(FileExistsError):
        execute_trial(
            make_plan(), trial, **fake_dependencies(events)
        )

    assert path.read_text() == "DO NOT OVERWRITE"
    assert events == []


@pytest.mark.parametrize(
    "changes",
    [
        {"dry_run": True},
        {"working_tree_clean": False},
        {
            "environment": "patched chess application",
            "patch_sha256": "abc",
        },
    ],
)
def test_rejects_unsafe_plan(tmp_path, changes):
    events = []

    with pytest.raises(ValueError):
        execute_trial(
            make_plan(**changes),
            make_trial(tmp_path),
            **fake_dependencies(events),
        )

    assert events == []


def test_sandbox_start_failure_is_recorded(tmp_path):
    trial = make_trial(tmp_path)
    events = []

    class BrokenSandbox:
        def __enter__(self):
            raise RuntimeError("Sandbox startup failed")

        def __exit__(self, *args):
            return False

    dependencies = fake_dependencies(events)
    dependencies["sandbox_factory"] = lambda **kw: BrokenSandbox()

    status = execute_trial(
        make_plan(), trial, **dependencies
    )

    assert status["outcome"] == "failed"
    assert "Sandbox startup failed" in status["error"]
    assert status["report_written"] is False
    assert json.loads(status_file(trial).read_text()) == status
