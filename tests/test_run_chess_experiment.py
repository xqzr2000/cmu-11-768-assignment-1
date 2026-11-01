"""Offline tests for the chess experiment planner."""

import hashlib
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from runpy import run_path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_chess_experiment.py"

build_plan = run_path(str(SCRIPT))["build_plan"]


def make_args(**overrides):
    values = {
        "experiment_id": "test-experiment",
        "model": "gpt-5-mini",
        "step_limit": 3,
        "trials": 1,
        "unpatched": True,
        "patch": None,
        "dry_run": True,
    }
    values.update(overrides)
    return Namespace(**values)


def mock_git(monkeypatch, status=""):
    def fake_git(*args):
        if args == ("status", "--porcelain"):
            return status
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        raise AssertionError(f"Unexpected git call: {args}")

    monkeypatch.setitem(
        build_plan.__globals__, "git", fake_git
    )


def test_unpatched_plan(monkeypatch):
    mock_git(monkeypatch)

    plan = build_plan(make_args())

    assert plan["model"] == "gpt-5-mini"
    assert plan["step_limit"] == 3
    assert plan["sample_count"] == 1
    assert plan["patch_sha256"] is None
    assert plan["working_tree_clean"] is True
    assert plan["harness_commit"] == "a" * 40
    assert plan["dry_run"] is True
    assert len(plan["trials"]) == 1


def test_multiple_trials_and_dirty_tree(monkeypatch):
    mock_git(monkeypatch, status="?? new_file.py")

    plan = build_plan(make_args(trials=3))

    assert plan["working_tree_clean"] is False
    assert plan["sample_count"] == 3
    assert [t["trial_id"] for t in plan["trials"]] == [
        "trial-001",
        "trial-002",
        "trial-003",
    ]

    paths = [t["trajectory"] for t in plan["trials"]]
    assert len(paths) == len(set(paths))


@pytest.mark.parametrize(
    "changes",
    [
        {"experiment_id": "../unsafe"},
        {"experiment_id": ""},
        {"step_limit": 0},
        {"trials": 0},
    ],
)
def test_invalid_configuration(changes):
    with pytest.raises(ValueError):
        build_plan(make_args(**changes))


def test_patch_fingerprint(tmp_path, monkeypatch):
    mock_git(monkeypatch)

    patch = tmp_path / "fix.patch"
    content = b"example patch contents\n"
    patch.write_bytes(content)

    plan = build_plan(make_args(
        unpatched=False,
        patch=patch,
    ))

    assert plan["patch_sha256"] == (
        hashlib.sha256(content).hexdigest()
    )
    assert plan["environment"] == (
        "patched chess application"
    )


@pytest.mark.parametrize("kind", ["missing", "empty"])
def test_missing_or_empty_patch(tmp_path, kind):
    patch = tmp_path / "fix.patch"

    if kind == "empty":
        patch.write_bytes(b"")

    with pytest.raises(ValueError):
        build_plan(make_args(
            unpatched=False,
            patch=patch,
        ))


def test_cli_dry_run(tmp_path):
    command = [
        sys.executable,
        str(SCRIPT),
        "--experiment-id", "cli-test",
        "--model", "gpt-5-mini",
        "--step-limit", "3",
        "--trials", "1",
        "--unpatched",
    ]

    # Without --dry-run, live execution is rejected.
    rejected = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "--dry-run" in rejected.stderr
    assert "--execute" in rejected.stderr

    # With --dry-run, a valid JSON plan is returned.
    completed = subprocess.run(
        command + ["--dry-run"],
        capture_output=True,
        text=True,
        check=True,
    )

    plan = json.loads(completed.stdout)
    assert plan["dry_run"] is True
    assert plan["experiment_id"] == "cli-test"
    assert len(plan["trials"]) == 1
