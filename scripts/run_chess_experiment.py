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

    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if not args.dry_run:
        parser.error("Live runs are not implemented; use --dry-run.")

    try:
        plan = build_plan(args)
    except ValueError as exc:
        parser.error(str(exc))

    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
