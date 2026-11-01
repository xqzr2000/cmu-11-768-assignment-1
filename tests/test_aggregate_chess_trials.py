"""Offline regression tests for chess trial aggregation."""

import json
from pathlib import Path
from runpy import run_path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "aggregate_chess_trials.py"
aggregate = run_path(str(SCRIPT))["aggregate"]


def make_plan(tmp_path, count=1):
    trials = [
        {
            "trial_id": f"trial-{i:03d}",
            "report": f"outputs/trial-{i:03d}-report.json",
        }
        for i in range(1, count + 1)
    ]

    plan = {
        "experiment_id": "synthetic-test",
        "model": "gpt-5-mini",
        "harness_commit": "a" * 40,
        "dry_run": False,
        "sample_count": count,
        "trials": trials,
    }

    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    return path, trials


def make_report(
    steps=3,
    attempts=3,
    accepted=3,
    errors=0,
    unknown=0,
    tokens=300,
    game_over=False,
):
    return {
        "model_steps": steps,
        "play_move_attempts": attempts,
        "accepted_moves": accepted,
        "tool_errors": errors,
        "unknown_outcomes": unknown,
        "recorded_action_tokens": tokens,
        "game_over": game_over,
    }


def save_trial(
    tmp_path,
    trial,
    *,
    outcome="step_limit",
    report=None,
    report_written=None,
    write_status=True,
):
    report_path = tmp_path / trial["report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if report is not None:
        report_path.write_text(json.dumps(report))

    if write_status:
        status_path = report_path.with_name(
            f"{trial['trial_id']}-status.json"
        )

        status = {
            "trial_id": trial["trial_id"],
            "outcome": outcome,
            "report_written": (
                report is not None
                if report_written is None
                else report_written
            ),
        }
        status_path.write_text(json.dumps(status))


def test_two_trial_aggregation(tmp_path):
    path, trials = make_plan(tmp_path, count=2)

    save_trial(
        tmp_path,
        trials[0],
        report=make_report(
            steps=2, attempts=2, accepted=2, tokens=100
        ),
    )

    save_trial(
        tmp_path,
        trials[1],
        outcome="completed",
        report=make_report(
            steps=3,
            attempts=3,
            accepted=2,
            errors=1,
            tokens=300,
            game_over=True,
        ),
    )

    result = aggregate(path, root=tmp_path)
    summary = result["summary"]

    assert result["planned_trials"] == 2
    assert result["reports_available"] == 2
    assert result["report_coverage"] == 1.0
    assert result["outcomes"] == {
        "completed": 1,
        "step_limit": 1,
    }
    assert summary["mean_model_steps"] == 2.5
    assert summary["total_play_move_attempts"] == 5
    assert summary["total_accepted_moves"] == 4
    assert summary["total_tool_errors"] == 1
    assert summary["observed_move_acceptance_rate"] == 0.8
    assert summary["mean_recorded_action_tokens"] == 200
    assert summary["completed_games"] == 1
    assert summary["observed_game_completion_rate"] == 0.5


def test_missing_trial_status(tmp_path):
    path, trials = make_plan(tmp_path, count=2)

    save_trial(tmp_path, trials[0], report=make_report())

    result = aggregate(path, root=tmp_path)

    assert result["reports_available"] == 1
    assert result["report_coverage"] == 0.5
    assert result["outcomes"]["missing_status"] == 1


def test_failed_trial_without_report(tmp_path):
    path, trials = make_plan(tmp_path)

    save_trial(
        tmp_path,
        trials[0],
        outcome="failed",
        report=None,
    )

    result = aggregate(path, root=tmp_path)

    assert result["outcomes"]["failed"] == 1
    assert result["reports_available"] == 0
    assert result["report_coverage"] == 0
    assert result["summary"]["mean_model_steps"] is None
    assert result["summary"]["mean_recorded_action_tokens"] is None


def test_report_status_inconsistency(tmp_path):
    path, trials = make_plan(tmp_path)

    save_trial(
        tmp_path,
        trials[0],
        report=None,
        report_written=True,
    )

    with pytest.raises(ValueError, match="inconsistency"):
        aggregate(path, root=tmp_path)


def test_report_without_status(tmp_path):
    path, trials = make_plan(tmp_path)

    save_trial(
        tmp_path,
        trials[0],
        report=make_report(),
        write_status=False,
    )

    with pytest.raises(ValueError, match="without status"):
        aggregate(path, root=tmp_path)


def test_invalid_move_totals(tmp_path):
    path, trials = make_plan(tmp_path)

    save_trial(
        tmp_path,
        trials[0],
        report=make_report(
            attempts=2,
            accepted=2,
            errors=1,
        ),
    )

    with pytest.raises(ValueError, match="do not add up"):
        aggregate(path, root=tmp_path)


def test_partial_token_usage(tmp_path):
    path, trials = make_plan(tmp_path, count=2)

    save_trial(
        tmp_path, trials[0],
        report=make_report(tokens=100),
    )
    save_trial(
        tmp_path, trials[1],
        report=make_report(tokens=None),
    )

    result = aggregate(path, root=tmp_path)

    assert result["reports_available"] == 2
    assert result["summary"]["token_usage_reports"] == 1
    assert result["summary"]["mean_recorded_action_tokens"] == 100


def test_duplicate_trial_ids(tmp_path):
    path, trials = make_plan(tmp_path, count=2)

    plan = json.loads(path.read_text())
    plan["trials"][1]["trial_id"] = trials[0]["trial_id"]
    path.write_text(json.dumps(plan))

    with pytest.raises(ValueError, match="Duplicate trial IDs"):
        aggregate(path, root=tmp_path)


def test_plan_trial_count_mismatch(tmp_path):
    path, _ = make_plan(tmp_path)

    plan = json.loads(path.read_text())
    plan["sample_count"] = 2
    path.write_text(json.dumps(plan))

    with pytest.raises(ValueError, match="Trial count"):
        aggregate(path, root=tmp_path)


def test_game_over_must_be_boolean(tmp_path):
    path, trials = make_plan(tmp_path)

    save_trial(
        tmp_path,
        trials[0],
        report=make_report(game_over=1),
    )

    with pytest.raises(ValueError, match="invalid game_over"):
        aggregate(path, root=tmp_path)
