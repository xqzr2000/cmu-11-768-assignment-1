"""Regression tests for chess evaluation comparisons."""

import json
import subprocess
import sys
from pathlib import Path
from runpy import run_path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_chess_evaluations.py"
compare = run_path(str(SCRIPT))["compare"]


def make_report(
    steps=2,
    attempts=2,
    accepted=2,
    errors=0,
    tokens=1000,
    game_over=False,
):
    return {
        "model_steps": steps,
        "play_move_attempts": attempts,
        "accepted_moves": accepted,
        "tool_errors": errors,
        "unknown_outcomes": 0,
        "recorded_action_tokens": tokens,
        "compactions": 0,
        "game_over": game_over,
    }


def save(tmp_path, name, report, **config):
    path = tmp_path / name
    data = {"evaluation": report, **config}
    path.write_text(json.dumps(data))
    return path


def test_identical_experiments(tmp_path):
    report = make_report()
    a = save(tmp_path, "a.json", report, sample_count=1)

    result = compare(a, a)

    for metric, values in result["metrics"].items():
        if metric != "game_over":
            assert values["delta"] == 0

    assert result["configuration_mismatches"] == {}
    assert result["warnings"]


def test_performance_deltas(tmp_path):
    baseline = save(
        tmp_path,
        "baseline.json",
        make_report(
            accepted=1,
            errors=1,
            tokens=1000,
        ),
        model="gpt-5-mini",
        environment="unpatched",
        step_limit=3,
        sample_count=5,
    )

    candidate = save(
        tmp_path,
        "candidate.json",
        make_report(
            accepted=2,
            errors=0,
            tokens=700,
            game_over=True,
        ),
        model="gpt-5-mini",
        environment="unpatched",
        step_limit=3,
        sample_count=5,
    )

    result = compare(baseline, candidate)
    metrics = result["metrics"]

    assert metrics["accepted_moves"]["delta"] == 1
    assert metrics["tool_errors"]["delta"] == -1
    assert metrics["recorded_action_tokens"]["delta"] == -300

    assert metrics["move_acceptance_rate"]["delta"] == 0.5
    assert metrics["tokens_per_step"]["delta"] == -150

    # Boolean outcomes should not be subtracted.
    assert metrics["game_over"]["delta"] is None
    assert result["configuration_mismatches"] == {}
    assert result["warnings"] == []


def test_configuration_mismatch(tmp_path):
    report = make_report()

    baseline = save(
        tmp_path,
        "baseline.json",
        report,
        model="gpt-5-mini",
        environment="unpatched",
        step_limit=3,
        sample_count=1,
    )

    candidate = save(
        tmp_path,
        "candidate.json",
        report,
        model="different-model",
        environment="patched",
        step_limit=5,
        sample_count=5,
    )

    result = compare(baseline, candidate)

    assert set(result["configuration_mismatches"]) == {
        "model",
        "environment",
        "step_limit",
        "sample_count",
    }

    assert any(
        "configurations differ" in warning
        for warning in result["warnings"]
    )


def test_missing_usage_and_zero_steps(tmp_path):
    report = make_report(
        steps=0,
        attempts=0,
        accepted=0,
        tokens=None,
    )

    # Test bare evaluation files without experiment metadata.
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))

    result = compare(path, path)
    metrics = result["metrics"]

    assert metrics["recorded_action_tokens"]["delta"] is None
    assert metrics["tokens_per_step"]["baseline"] is None
    assert metrics["move_acceptance_rate"]["baseline"] is None


def test_cli_writes_comparison(tmp_path):
    report = make_report()

    baseline = save(tmp_path, "baseline.json", report)
    candidate = save(tmp_path, "candidate.json", report)
    output = tmp_path / "comparison.json"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(baseline),
            str(candidate),
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    saved = json.loads(output.read_text())

    assert output.exists()
    assert saved["metrics"]["accepted_moves"]["delta"] == 0


def test_missing_configuration_detected(tmp_path):
    report = make_report()

    baseline = save(
        tmp_path,
        "baseline.json",
        report,
        model="gpt-5-mini",
        environment="unpatched",
        step_limit=3,
        sample_count=5,
    )

    candidate = save(
        tmp_path,
        "candidate.json",
        report,
        environment="unpatched",
        step_limit=3,
        sample_count=5,
    )

    result = compare(baseline, candidate)

    assert result["configuration_mismatches"] == {}
    assert result["missing_configuration"] == {
        "model": {
            "baseline": "gpt-5-mini",
            "candidate": None,
        }
    }
    assert any(
        "metadata is missing" in warning
        for warning in result["warnings"]
    )
