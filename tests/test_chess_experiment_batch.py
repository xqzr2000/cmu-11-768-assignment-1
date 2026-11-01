"""Offline tests for multi-trial experiment orchestration."""

import json
from pathlib import Path
from runpy import run_path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_chess_experiment.py"
execute_experiment = run_path(str(SCRIPT))["execute_experiment"]


def make_experiment(tmp_path, monkeypatch, count=3):
    monkeypatch.setitem(
        execute_experiment.__globals__, "ROOT", tmp_path
    )

    directory = tmp_path / "artifacts" / "eval-harness" / "batch-test"
    directory.mkdir(parents=True)

    trials = []
    for i in range(1, count + 1):
        trial_id = f"trial-{i:03d}"
        trials.append({
            "trial_id": trial_id,
            "trajectory": str(directory / f"{trial_id}-trajectory.json"),
            "result": str(directory / f"{trial_id}-result.json"),
            "report": str(directory / f"{trial_id}-report.json"),
        })

    plan = {
        "experiment_id": "batch-test",
        "model": "gpt-5-mini",
        "harness_commit": "a" * 40,
        "dry_run": False,
        "working_tree_clean": True,
        "sample_count": count,
        "trials": trials,
    }

    plan_path = directory / "plan.json"
    plan_path.write_text(json.dumps(plan) + "\n")

    return plan, plan_path


def status_path(trial):
    return Path(trial["report"]).with_name(
        f"{trial['trial_id']}-status.json"
    )


def save_success(
    trial,
    *,
    outcome="step_limit",
    steps=3,
    attempts=3,
    accepted=3,
    errors=0,
    tokens=300,
):
    report = {
        "model_steps": steps,
        "play_move_attempts": attempts,
        "accepted_moves": accepted,
        "tool_errors": errors,
        "unknown_outcomes": 0,
        "recorded_action_tokens": tokens,
        "game_over": outcome == "completed",
    }

    Path(trial["report"]).write_text(json.dumps(report))

    status = {
        "trial_id": trial["trial_id"],
        "outcome": outcome,
        "error": None,
        "model_steps": steps,
        "game_over": report["game_over"],
        "report_written": True,
    }

    status_path(trial).write_text(json.dumps(status))


def test_three_trials_continue_after_failure(tmp_path, monkeypatch):
    plan, plan_path = make_experiment(tmp_path, monkeypatch)
    executed = []

    def fake_executor(plan, trial):
        trial_id = trial["trial_id"]
        executed.append(trial_id)

        if trial_id == "trial-001":
            save_success(
                trial,
                outcome="completed",
                steps=2,
                attempts=2,
                accepted=2,
                tokens=100,
            )
        elif trial_id == "trial-002":
            raise RuntimeError("Simulated trial failure")
        else:
            save_success(
                trial,
                outcome="step_limit",
                steps=3,
                attempts=3,
                accepted=2,
                errors=1,
                tokens=300,
            )

    summary = execute_experiment(
        plan, plan_path, trial_executor=fake_executor
    )

    assert executed == [
        "trial-001", "trial-002", "trial-003"
    ]

    assert summary["planned_trials"] == 3
    assert summary["reports_available"] == 2
    assert summary["report_coverage"] == pytest.approx(2 / 3)
    assert summary["outcomes"] == {
        "completed": 1,
        "failed": 1,
        "step_limit": 1,
    }

    metrics = summary["summary"]
    assert metrics["total_play_move_attempts"] == 5
    assert metrics["total_accepted_moves"] == 4
    assert metrics["total_tool_errors"] == 1
    assert metrics["observed_move_acceptance_rate"] == 0.8
    assert metrics["mean_recorded_action_tokens"] == 200
    assert metrics["completed_games"] == 1

    failure = json.loads(
        status_path(plan["trials"][1]).read_text()
    )
    assert failure["outcome"] == "failed"
    assert "Simulated trial failure" in failure["error"]

    saved = json.loads(
        plan_path.with_name("summary.json").read_text()
    )
    assert saved == summary


@pytest.mark.parametrize(
    "output_name",
    ["trajectory", "result", "report", "status"],
)
def test_preflight_refuses_existing_outputs(
    tmp_path, monkeypatch, output_name
):
    plan, plan_path = make_experiment(tmp_path, monkeypatch)
    trial = plan["trials"][1]

    path = (
        status_path(trial)
        if output_name == "status"
        else Path(trial[output_name])
    )
    path.write_text("DO NOT OVERWRITE")

    executed = []

    with pytest.raises(FileExistsError):
        execute_experiment(
            plan,
            plan_path,
            trial_executor=lambda p, t: executed.append(t),
        )

    assert executed == []
    assert path.read_text() == "DO NOT OVERWRITE"


def test_saved_plan_must_match(tmp_path, monkeypatch):
    plan, plan_path = make_experiment(tmp_path, monkeypatch)
    plan["model"] = "different-model"

    with pytest.raises(ValueError, match="Saved plan differs"):
        execute_experiment(
            plan, plan_path, trial_executor=lambda p, t: None
        )


def test_missing_status_becomes_failure(tmp_path, monkeypatch):
    plan, plan_path = make_experiment(
        tmp_path, monkeypatch, count=1
    )

    summary = execute_experiment(
        plan,
        plan_path,
        trial_executor=lambda p, t: None,
    )

    assert summary["planned_trials"] == 1
    assert summary["reports_available"] == 0
    assert summary["outcomes"] == {"failed": 1}

    failure = json.loads(
        status_path(plan["trials"][0]).read_text()
    )
    assert "did not write its status" in failure["error"]


def test_inconsistent_report_rejected(tmp_path, monkeypatch):
    plan, plan_path = make_experiment(
        tmp_path, monkeypatch, count=1
    )

    def bad_executor(plan, trial):
        status_path(trial).write_text(json.dumps({
            "trial_id": trial["trial_id"],
            "outcome": "completed",
            "report_written": True,
        }))

    with pytest.raises(ValueError, match="inconsistency"):
        execute_experiment(
            plan, plan_path, trial_executor=bad_executor
        )

    assert not plan_path.with_name("summary.json").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"dry_run": True},
        {"working_tree_clean": False},
        {"sample_count": 0},
    ],
)
def test_rejects_invalid_plan(tmp_path, monkeypatch, changes):
    plan, plan_path = make_experiment(tmp_path, monkeypatch)
    plan.update(changes)

    with pytest.raises(ValueError):
        execute_experiment(
            plan, plan_path, trial_executor=lambda p, t: None
        )


def test_rejects_duplicate_trial_ids(tmp_path, monkeypatch):
    plan, plan_path = make_experiment(tmp_path, monkeypatch)
    plan["trials"][1]["trial_id"] = "trial-001"
    plan_path.write_text(json.dumps(plan))

    with pytest.raises(ValueError, match="Duplicate trial IDs"):
        execute_experiment(
            plan, plan_path, trial_executor=lambda p, t: None
        )


def test_refuses_existing_summary(tmp_path, monkeypatch):
    plan, plan_path = make_experiment(tmp_path, monkeypatch)
    summary_path = plan_path.with_name("summary.json")
    summary_path.write_text("DO NOT OVERWRITE")

    with pytest.raises(FileExistsError):
        execute_experiment(
            plan, plan_path, trial_executor=lambda p, t: None
        )

    assert summary_path.read_text() == "DO NOT OVERWRITE"
