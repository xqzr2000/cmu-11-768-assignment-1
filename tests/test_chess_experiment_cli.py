"""Offline tests for chess experiment CLI orchestration."""

import json
import sys
from pathlib import Path
from runpy import run_path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_chess_experiment.py"
main = run_path(str(SCRIPT))["main"]

BASE_ARGS = [
    "--experiment-id", "cli-test",
    "--model", "gpt-5-mini",
    "--step-limit", "3",
    "--trials", "1",
    "--unpatched",
]


def configure_cli(
    monkeypatch,
    tmp_path,
    args,
    *,
    dirty=False,
    outcome="completed",
):
    """Use real CLI logic but fake Git and trial execution."""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT), *args]
    )

    namespace = main.__globals__
    monkeypatch.setitem(namespace, "ROOT", tmp_path)

    def fake_git(*arguments):
        if arguments == ("status", "--porcelain"):
            return " M tracked.py" if dirty else ""
        if arguments == ("rev-parse", "HEAD"):
            return "a" * 40
        raise AssertionError(arguments)

    monkeypatch.setitem(namespace, "git", fake_git)

    calls = []

    def fake_execute(plan, trial):
        calls.append((plan, trial))
        return {
            "trial_id": trial["trial_id"],
            "outcome": outcome,
            "error": "Simulated failure" if outcome == "failed" else None,
            "model_steps": 3,
            "game_over": False,
            "report_written": outcome != "failed",
        }

    monkeypatch.setitem(
        namespace, "execute_trial", fake_execute
    )

    return calls


def test_execute_dispatches_one_trial(
    tmp_path, monkeypatch, capsys
):
    calls = configure_cli(
        monkeypatch, tmp_path, BASE_ARGS + ["--execute"]
    )

    main()

    assert len(calls) == 1
    plan, trial = calls[0]

    assert plan["dry_run"] is False
    assert plan["working_tree_clean"] is True
    assert plan["model"] == "gpt-5-mini"
    assert plan["step_limit"] == 3
    assert trial["trial_id"] == "trial-001"

    plan_file = (
        tmp_path / "artifacts/eval-harness/cli-test/plan.json"
    )
    saved = json.loads(plan_file.read_text())

    assert saved["harness_commit"] == "a" * 40
    assert saved["dry_run"] is False

    status = json.loads(capsys.readouterr().out)
    assert status["outcome"] == "completed"


def test_step_limit_is_not_cli_failure(
    tmp_path, monkeypatch, capsys
):
    calls = configure_cli(
        monkeypatch,
        tmp_path,
        BASE_ARGS + ["--execute"],
        outcome="step_limit",
    )

    main()

    assert len(calls) == 1
    status = json.loads(capsys.readouterr().out)
    assert status["outcome"] == "step_limit"


def test_failed_trial_exits_nonzero(
    tmp_path, monkeypatch, capsys
):
    calls = configure_cli(
        monkeypatch,
        tmp_path,
        BASE_ARGS + ["--execute"],
        outcome="failed",
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
    assert len(calls) == 1

    status = json.loads(capsys.readouterr().out)
    assert status["outcome"] == "failed"


def test_dirty_tree_rejected(
    tmp_path, monkeypatch
):
    calls = configure_cli(
        monkeypatch,
        tmp_path,
        BASE_ARGS + ["--execute"],
        dirty=True,
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert calls == []
    assert not (
        tmp_path / "artifacts/eval-harness/cli-test/plan.json"
    ).exists()


def test_existing_output_rejected(
    tmp_path, monkeypatch
):
    calls = configure_cli(
        monkeypatch,
        tmp_path,
        BASE_ARGS + ["--execute"],
    )

    plan_file = (
        tmp_path / "artifacts/eval-harness/cli-test/plan.json"
    )
    plan_file.parent.mkdir(parents=True)
    plan_file.write_text("DO NOT OVERWRITE")

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert calls == []
    assert plan_file.read_text() == "DO NOT OVERWRITE"


@pytest.mark.parametrize(
    "args",
    [
        [
            "--experiment-id", "cli-test",
            "--model", "gpt-5-mini",
            "--patch", "fix.patch",
            "--execute",
        ],
    ],
)
def test_unsupported_live_configuration(
    tmp_path, monkeypatch, args
):
    calls = configure_cli(
        monkeypatch, tmp_path, args
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert calls == []


def test_dry_run_does_not_execute(
    tmp_path, monkeypatch, capsys
):
    calls = configure_cli(
        monkeypatch,
        tmp_path,
        BASE_ARGS + ["--dry-run"],
    )

    main()

    plan = json.loads(capsys.readouterr().out)

    assert plan["dry_run"] is True
    assert len(plan["trials"]) == 1
    assert calls == []
    assert not (
        tmp_path / "artifacts/eval-harness/cli-test/plan.json"
    ).exists()


BATCH_ARGS = [
    "--experiment-id", "cli-test",
    "--model", "gpt-5-mini",
    "--step-limit", "3",
    "--trials", "3",
    "--unpatched",
    "--execute",
]


def test_batch_cli_dispatch(tmp_path, monkeypatch, capsys):
    single_calls = configure_cli(
        monkeypatch, tmp_path, BATCH_ARGS
    )
    batch_calls = []

    def fake_batch(plan, plan_path):
        batch_calls.append((plan, plan_path))
        assert plan_path.is_file()

        return {
            "experiment_id": "cli-test",
            "planned_trials": 3,
            "outcomes": {"step_limit": 3},
        }

    monkeypatch.setitem(
        main.__globals__, "execute_experiment", fake_batch
    )

    main()

    assert single_calls == []
    assert len(batch_calls) == 1

    plan, plan_path = batch_calls[0]
    assert plan["sample_count"] == 3
    assert plan["dry_run"] is False

    saved = json.loads(plan_path.read_text())
    assert saved == plan

    summary = json.loads(capsys.readouterr().out)
    assert summary["planned_trials"] == 3
    assert summary["outcomes"]["step_limit"] == 3


def test_batch_cli_failure_exit(tmp_path, monkeypatch, capsys):
    configure_cli(monkeypatch, tmp_path, BATCH_ARGS)

    def fake_batch(plan, plan_path):
        return {
            "experiment_id": "cli-test",
            "planned_trials": 3,
            "outcomes": {
                "step_limit": 2,
                "failed": 1,
            },
        }

    monkeypatch.setitem(
        main.__globals__, "execute_experiment", fake_batch
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1

    summary = json.loads(capsys.readouterr().out)
    assert summary["outcomes"]["failed"] == 1


def test_batch_rejects_existing_later_output(
    tmp_path, monkeypatch
):
    configure_cli(monkeypatch, tmp_path, BATCH_ARGS)

    output = (
        tmp_path
        / "artifacts/eval-harness/cli-test"
        / "trial-002-report.json"
    )
    output.parent.mkdir(parents=True)
    output.write_text("DO NOT OVERWRITE")

    def unexpected_batch(plan, plan_path):
        pytest.fail("Batch execution must not start.")

    monkeypatch.setitem(
        main.__globals__, "execute_experiment",
        unexpected_batch,
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert output.read_text() == "DO NOT OVERWRITE"
    assert not (output.parent / "plan.json").exists()
