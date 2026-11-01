"""Plan reproducible chess experiments.

Live execution will be added after dry-run validation.
"""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def git(*arguments):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments],
        text=True,
    ).strip()


def build_plan(args):
    if args.step_limit < 1 or args.trials < 1:
        raise ValueError("Step limit and trials must be positive.")

    if not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9_-]*",
        args.experiment_id,
    ):
        raise ValueError("Invalid experiment ID.")

    if args.unpatched:
        environment = "original chess application, no patch"
        patch_sha256 = None
    else:
        if not args.patch.is_file():
            raise ValueError(f"Patch not found: {args.patch}")

        patch_bytes = args.patch.read_bytes()
        if not patch_bytes:
            raise ValueError("Patch cannot be empty.")

        environment = "patched chess application"
        patch_sha256 = hashlib.sha256(
            patch_bytes
        ).hexdigest()

    clean = not bool(git("status", "--porcelain"))

    output_dir = (
        Path("artifacts/eval-harness")
        / args.experiment_id
    )

    return {
        "experiment_id": args.experiment_id,
        "model": args.model,
        "environment": environment,
        "step_limit": args.step_limit,
        "sample_count": args.trials,
        "harness_commit": git("rev-parse", "HEAD"),
        "working_tree_clean": clean,
        "patch_sha256": patch_sha256,
        "chess_agent": {
            "model": args.model,
            "programmatic_tools": False,
            "include_legal_moves": True,
            "skills_path": None,
        },
        "harness_developer": {
            "tool": None,
            "model": None,
        },
        "trials": [
            {
                "trial_id": f"trial-{i:03d}",
                "trajectory": str(
                    output_dir / f"trial-{i:03d}-trajectory.json"
                ),
                "result": str(
                    output_dir / f"trial-{i:03d}-result.json"
                ),
                "report": str(
                    output_dir / f"trial-{i:03d}-report.json"
                ),
            }
            for i in range(1, args.trials + 1)
        ],
        "dry_run": True,
    }




def execute_trial(
    plan,
    trial,
    *,
    sandbox_factory=None,
    agent_factory=None,
    observation_recorder=None,
    evaluator=None,
):
    """Execute one isolated trial and preserve its outcome.

    Dependencies may be replaced by fakes in offline tests.
    """

    if plan.get("dry_run") is not False:
        raise ValueError("Live execution requires an explicit live plan.")

    if not plan.get("working_tree_clean"):
        raise ValueError("Live execution requires a clean working tree.")

    if (
        plan["environment"] != "original chess application, no patch"
        or plan["patch_sha256"] is not None
    ):
        raise ValueError("Only unpatched trials are supported for now.")

    trajectory = Path(trial["trajectory"])
    result = Path(trial["result"])
    report = Path(trial["report"])
    status_path = report.with_name(
        f"{trial['trial_id']}-status.json"
    )

    outputs = (trajectory, result, report, status_path)
    if any(path.exists() for path in outputs):
        raise FileExistsError("Trial output already exists; refusing overwrite.")

    from assignment.agent.base import StepLimitError

    if sandbox_factory is None:
        from assignment.chess_sandbox import ChessSandbox
        sandbox_factory = ChessSandbox

    if agent_factory is None:
        from assignment.agent import ChessAgent
        agent_factory = ChessAgent

    if observation_recorder is None:
        from assignment.cli import _record_final_observations
        observation_recorder = _record_final_observations

    if evaluator is None:
        from runpy import run_path
        evaluator = run_path(
            str(ROOT / "scripts" / "eval_chess_trajectory.py")
        )["evaluate"]

    status_path.parent.mkdir(parents=True, exist_ok=True)

    status = {
        "trial_id": trial["trial_id"],
        "outcome": "failed",
        "error": None,
        "model_steps": 0,
        "game_over": None,
        "report_written": False,
    }

    try:
        with sandbox_factory(
            patch=None,
            deployment_timeout=600,
        ) as sandbox:
            agent = agent_factory(
                environment=sandbox,
                model=plan["model"],
                logs_save_path=str(trajectory),
                step_limit=plan["step_limit"],
                auto_stop_environment=False,
                programmatic_tools=plan["chess_agent"]["programmatic_tools"],
                include_legal_moves=plan["chess_agent"]["include_legal_moves"],
                skills_path=plan["chess_agent"]["skills_path"],
            )

            try:
                agent.run()
                status["outcome"] = (
                    "completed" if agent.finished else "stopped"
                )
            except StepLimitError as exc:
                status["outcome"] = "step_limit"
                status["error"] = str(exc)
            finally:
                status["model_steps"] = agent.steps_taken
                status["game_over"] = (
                    (agent.last_state or {}).get("game_over")
                )
                observation_recorder(trajectory, agent)
                result.parent.mkdir(parents=True, exist_ok=True)
                result.write_text(
                    json.dumps(agent.last_state or {}, indent=2) + "\n"
                )

        if not trajectory.is_file():
            raise RuntimeError("Trajectory was not saved.")

        metrics = evaluator(trajectory, result)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(metrics, indent=2) + "\n"
        )
        status["report_written"] = True

    except Exception as exc:
        status["outcome"] = "failed"
        status["error"] = f"{type(exc).__name__}: {exc}"

    finally:
        status_path.write_text(
            json.dumps(status, indent=2) + "\n"
        )

    return status




def execute_experiment(
    plan,
    plan_path,
    *,
    trial_executor=None,
    aggregator=None,
):
    """Execute planned trials sequentially and aggregate results."""

    from runpy import run_path

    if plan.get("dry_run") is not False:
        raise ValueError("Expected a live experiment plan.")

    if plan.get("working_tree_clean") is not True:
        raise ValueError("Live execution requires a clean working tree.")

    trials = plan.get("trials", [])
    if not trials or len(trials) != plan.get("sample_count"):
        raise ValueError("Invalid experiment trial count.")

    ids = [trial["trial_id"] for trial in trials]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate trial IDs.")

    plan_path = Path(plan_path)
    if not plan_path.is_file():
        raise ValueError("Experiment plan must be saved first.")

    saved_plan = json.loads(plan_path.read_text())
    if saved_plan != plan:
        raise ValueError("Saved plan differs from execution plan.")

    summary_path = plan_path.with_name("summary.json")
    if summary_path.exists():
        raise FileExistsError("Experiment summary already exists.")

    def resolve(value):
        value = Path(value)
        return value if value.is_absolute() else ROOT / value

    # Check every output before starting the first trial.
    expected_directory = plan_path.parent.resolve()
    reserved_paths = set()

    for trial in trials:
        report_path = resolve(trial["report"])
        status_path = report_path.with_name(
            f"{trial['trial_id']}-status.json"
        )

        paths = [
            resolve(trial["trajectory"]),
            resolve(trial["result"]),
            report_path,
            status_path,
        ]

        for output in paths:
            normalized = output.resolve()
            if normalized.parent != expected_directory:
                raise ValueError("Trial output outside experiment directory.")
            if normalized in reserved_paths:
                raise ValueError("Duplicate trial output path.")
            if output.exists():
                raise FileExistsError(
                    f"Trial output already exists: {output}"
                )
            reserved_paths.add(normalized)

    if trial_executor is None:
        trial_executor = execute_trial

    if aggregator is None:
        aggregation_script = (
            Path(__file__).resolve().parent
            / "aggregate_chess_trials.py"
        )
        aggregator = run_path(str(aggregation_script))["aggregate"]

    # Each trial is executed independently.
    for trial in trials:
        trial_id = trial["trial_id"]
        status_path = resolve(trial["report"]).with_name(
            f"{trial_id}-status.json"
        )

        try:
            trial_executor(plan, trial)

            if not status_path.is_file():
                raise RuntimeError(
                    "Trial executor did not write its status."
                )

        except Exception as exc:
            # Preserve an unexpected orchestration failure.
            # Do not overwrite a status that already exists.
            if not status_path.exists():
                status_path.parent.mkdir(
                    parents=True, exist_ok=True
                )

                failure = {
                    "trial_id": trial_id,
                    "outcome": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "model_steps": 0,
                    "game_over": None,
                    "report_written": False,
                }

                status_path.write_text(
                    json.dumps(failure, indent=2) + "\n"
                )

        # Continue to the next trial even after a failure.

    summary = aggregator(plan_path, root=ROOT)

    # Exclusive creation prevents overwriting a prior summary.
    with summary_path.open("x") as output:
        json.dump(summary, output, indent=2)
        output.write("\n")

    return summary



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--step-limit", type=int, default=3)
    parser.add_argument("--trials", type=int, default=1)

    environment = parser.add_mutually_exclusive_group(
        required=True
    )
    environment.add_argument("--unpatched", action="store_true")
    environment.add_argument("--patch", type=Path)

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")

    args = parser.parse_args()

    if args.execute:
        if not args.unpatched:
            parser.error("Live execution supports unpatched chess only.")
        if Path.cwd().resolve() != ROOT:
            parser.error("Run live experiments from the repository root.")

    try:
        plan = build_plan(args)
    except ValueError as exc:
        parser.error(str(exc))

    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return

    if not plan["working_tree_clean"]:
        parser.error(
            "Commit or discard working-tree changes before live execution."
        )

    trials = plan["trials"]
    output_dir = Path(trials[0]["trajectory"]).parent
    plan_path = output_dir / "plan.json"
    summary_path = output_dir / "summary.json"

    # Preflight every planned output before execution.
    outputs = [plan_path, summary_path]

    for trial in trials:
        report = Path(trial["report"])
        status_path = report.with_name(
            f"{trial['trial_id']}-status.json"
        )

        outputs.extend([
            Path(trial["trajectory"]),
            Path(trial["result"]),
            report,
            status_path,
        ])

    if any(path.exists() for path in outputs):
        parser.error("Experiment output already exists.")

    plan["dry_run"] = False

    output_dir.mkdir(parents=True, exist_ok=True)

    # Exclusive creation prevents overwriting an existing plan.
    with plan_path.open("x") as output:
        json.dump(plan, output, indent=2)
        output.write("\n")

    if len(trials) == 1:
        # Preserve existing single-trial behavior.
        status = execute_trial(plan, trials[0])
        print(json.dumps(status, indent=2))

        if status["outcome"] == "failed":
            raise SystemExit(1)
    else:
        # Execute and aggregate multiple independent trials.
        summary = execute_experiment(plan, plan_path)
        print(json.dumps(summary, indent=2))

        unexpected_failures = sum(
            count
            for outcome, count in summary["outcomes"].items()
            if outcome not in (
                "completed", "step_limit", "stopped"
            )
        )

        if unexpected_failures:
            raise SystemExit(1)

if __name__ == "__main__":
    main()
