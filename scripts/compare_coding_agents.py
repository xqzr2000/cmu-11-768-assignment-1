"""Run and compare two coding agents on the Part 1 chess task.

* ``codeagent`` — the assignment's own CodeAgent (our ReAct harness), using the
  OpenAI-compatible API configured by OPENAI_BASE_URL / OPENAI_API_KEY /
  OPENAI_MODEL (for example DeepSeek). Billable.
* ``opencode`` — OpenCode in the same kind of disposable Docker sandbox, using
  an OpenCode free model. It is launched with every credential and provider
  variable stripped from its environment, never gets ``--allow-paid-model``,
  and the sandbox refuses to start if anything credential-like is visible.

Each trial goes to ``artifacts/compare/<task>/<agent>/trial-<n>/`` (git-ignored)
and its patch is graded by the same evaluator as ``make check-part1``. The graded
``artifacts/fix.patch`` and ``artifacts/part1-trajectory.json`` are never written.

    # register the Part 1 run you already did as CodeAgent trial 1
    uv run python scripts/compare_coding_agents.py import-codeagent --trial 1 \
        --patch artifacts/fix.patch --trajectory artifacts/part1-trajectory.json
    # one paid CodeAgent trial (endpoint/model from the environment)
    uv run python scripts/compare_coding_agents.py run codeagent --trial 2
    # one free OpenCode trial (probes the free quota first)
    uv run python scripts/compare_coding_agents.py run opencode --trial 1
    # Markdown summary; optionally write it into the docs report
    uv run python scripts/compare_coding_agents.py report \
        --update-doc docs/Coding-Agent-Comparison.md
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from assignment.compare import (
    DEFAULT_ROOT, codeagent_metrics, evaluation_summary, load_records, opencode_metrics,
    patch_stats, render_report, sanitized_env, trial_dir, update_doc,
)
from assignment.opencode_runner import (
    DEFAULT_FREE_MODEL, DEFAULT_TIMEOUT, credential_like_names, is_free_opencode_model,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_TASK = Path("tasks/chess-terminal-move")
CODE_SKILLS = Path("tasks/code-skills")
GRADED = {(REPO / "artifacts/fix.patch").resolve(), (REPO / "artifacts/part1-trajectory.json").resolve()}


def _git_head() -> str | None:
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                            capture_output=True, text=True)
    return result.stdout.strip() or None


def _endpoint_host() -> str:
    return urlparse(os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").hostname or "?"


def _prepare(directory: Path, force: bool) -> None:
    if directory.exists():
        if not force:
            raise SystemExit(f"{directory} already exists; pick another --trial or pass --force")
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def _stream(argv: list[str], env: dict[str, str], log: Path) -> tuple[int, float]:
    """Run a process, echoing and saving its output; return (exit code, seconds)."""
    started = time.monotonic()
    with log.open("w") as handle:
        process = subprocess.Popen(argv, cwd=REPO, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            handle.write(line)
        code = process.wait()
    return code, round(time.monotonic() - started, 1)


def _evaluate(task_path: Path, patch_path: Path, out: Path) -> dict | None:
    """Replay the patch in a fresh container, exactly like ``make check-part1``."""
    if not patch_path.is_file() or not patch_path.read_text().strip():
        return None
    from assignment.eval import EvaluationSpec, Task, evaluate

    report = evaluate(EvaluationSpec.load(task_path / "public_tests"),
                      patch=patch_path.read_text(), task=Task.load(task_path), timeout=600)
    out.write_text(report.summary() + "\n")
    print(report.summary())
    return evaluation_summary(report)


def _finish(directory: Path, record: dict, task_path: Path) -> dict:
    patch_path = directory / "fix.patch"
    record["patch"] = patch_stats(patch_path.read_text()) if patch_path.is_file() else None
    record["evaluation"] = _evaluate(task_path, patch_path, directory / "evaluation.txt")
    (directory / "run.json").write_text(json.dumps(record, indent=2))
    print(f"Recorded {directory / 'run.json'}")
    return record


def _base_record(agent: str, trial: int, task_id: str) -> dict:
    return {
        "task_id": task_id, "agent": agent, "trial": trial,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "harness_commit": _git_head(),
    }


def run_codeagent(args) -> int:
    model = os.environ.get("OPENAI_MODEL")
    if not model or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("CodeAgent needs OPENAI_MODEL and OPENAI_API_KEY (e.g. via your ds() helper).")
    from assignment.task import Task

    task_id = Task.load(args.task).id
    directory = trial_dir(args.root, task_id, "codeagent", args.trial)
    _prepare(directory, args.force)
    patch, trajectory = directory / "fix.patch", directory / "trajectory.json"
    assert patch.resolve() not in GRADED and trajectory.resolve() not in GRADED
    print(f"CodeAgent trial {args.trial}: model {model} via {_endpoint_host()} (billable)")
    argv = [sys.executable, "-c", "from assignment.cli import run_code_agent; run_code_agent()",
            "--task", str(args.task), "--step-limit", str(args.step_limit),
            "--skills-path", str(CODE_SKILLS),
            "--trajectory", str(trajectory), "--patch-output", str(patch)]
    code, seconds = _stream(argv, dict(os.environ), directory / "console.log")
    record = _base_record("codeagent", args.trial, task_id)
    record.update(model=model, endpoint=_endpoint_host(), uses_paid_api=True,
                  step_limit=args.step_limit, exit_code=code, wall_seconds=seconds)
    record["status"] = "ok" if code == 0 and patch.is_file() else ("no_patch" if code == 0 else "error")
    record["metrics"] = (codeagent_metrics(json.loads(trajectory.read_text()))
                         if trajectory.is_file() else None)
    _finish(directory, record, args.task)
    return 0 if record["status"] == "ok" else 1


def import_codeagent(args) -> int:
    from assignment.task import Task

    task_id = Task.load(args.task).id
    directory = trial_dir(args.root, task_id, "codeagent", args.trial)
    _prepare(directory, args.force)
    shutil.copyfile(args.patch, directory / "fix.patch")
    shutil.copyfile(args.trajectory, directory / "trajectory.json")
    record = _base_record("codeagent", args.trial, task_id)
    record.update(model=args.model, endpoint=args.endpoint, uses_paid_api=True,
                  step_limit=args.step_limit, exit_code=0, wall_seconds=None,
                  status="ok", imported_from=[str(args.patch), str(args.trajectory)])
    record["metrics"] = codeagent_metrics(json.loads(args.trajectory.read_text()))
    _finish(directory, record, args.task)
    return 0


def run_opencode(args) -> int:
    if not is_free_opencode_model(args.model):
        raise SystemExit(f"{args.model!r} is not an OpenCode free model; the comparison never uses a paid API.")
    from assignment.task import Task

    task_id = Task.load(args.task).id
    env = sanitized_env(os.environ)
    leftover = credential_like_names(env)
    if leftover:  # sanitized_env should make this impossible; belt and braces
        raise SystemExit("Refusing to start: credential-like variables remain: " + ", ".join(leftover))
    script = str(REPO / "scripts/run_opencode.py")

    if not args.skip_probe:
        print(f"Probing {args.model} (free quota check, no API key)...")
        code = subprocess.run([sys.executable, script, "--probe", "--model", args.model],
                              cwd=REPO, env=env).returncode
        if code != 0:
            print("Probe failed: the free model did not answer. No trial recorded.", file=sys.stderr)
            return 1

    directory = trial_dir(args.root, task_id, "opencode", args.trial)
    _prepare(directory, args.force)
    patch, log = directory / "fix.patch", directory / "opencode-run.json"
    print(f"OpenCode trial {args.trial}: model {args.model} (free, no credentials)")
    argv = [sys.executable, script, "--task", str(args.task), "--model", args.model,
            "--timeout", str(args.timeout), "--patch-output", str(patch), "--trajectory", str(log)]
    code, seconds = _stream(argv, env, directory / "console.log")
    run_log = json.loads(log.read_text()) if log.is_file() else {}
    if run_log.get("credential_variables_forwarded"):
        raise SystemExit("OpenCode log reports forwarded credentials; treat this trial as invalid.")
    record = _base_record("opencode", args.trial, task_id)
    record.update(model=args.model, endpoint="opencode free tier", uses_paid_api=False,
                  timeout=args.timeout, exit_code=code, wall_seconds=seconds,
                  opencode_version=run_log.get("opencode_version"))
    record["status"] = run_log.get("status") or ("ok" if code == 0 and patch.is_file() else "error")
    record["metrics"] = opencode_metrics(run_log) if run_log else None
    _finish(directory, record, args.task)
    return 0 if record["status"] == "ok" else 1


def report(args) -> int:
    from assignment.task import Task

    task_id = Task.load(args.task).id
    markdown = render_report(load_records(args.root, task_id), task_id)
    print(markdown)
    if args.update_doc:
        update_doc(args.update_doc, markdown)
        print(f"Updated {args.update_doc}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--task", type=Path, default=DEFAULT_TASK)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one trial of one agent")
    run_sub = run.add_subparsers(dest="agent", required=True)
    code = run_sub.add_parser("codeagent", help="CodeAgent via the configured API (billable)")
    code.add_argument("--trial", type=int, required=True)
    code.add_argument("--step-limit", type=int, default=200)
    code.add_argument("--force", action="store_true")
    code.set_defaults(func=run_codeagent)
    oc = run_sub.add_parser("opencode", help="OpenCode with a free model (never a paid API)")
    oc.add_argument("--trial", type=int, required=True)
    oc.add_argument("--model", default=os.getenv("OPENCODE_MODEL", DEFAULT_FREE_MODEL))
    oc.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    oc.add_argument("--skip-probe", action="store_true")
    oc.add_argument("--force", action="store_true")
    oc.set_defaults(func=run_opencode)

    imp = sub.add_parser("import-codeagent", help="register an existing CodeAgent run as a trial")
    imp.add_argument("--trial", type=int, required=True)
    imp.add_argument("--patch", type=Path, required=True)
    imp.add_argument("--trajectory", type=Path, required=True)
    imp.add_argument("--model", default="deepseek-flash")
    imp.add_argument("--endpoint", default="api.deepseek.com")
    imp.add_argument("--step-limit", type=int, default=200)
    imp.add_argument("--force", action="store_true")
    imp.set_defaults(func=import_codeagent)

    rep = sub.add_parser("report", help="print the Markdown comparison")
    rep.add_argument("--update-doc", type=Path)
    rep.set_defaults(func=report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
