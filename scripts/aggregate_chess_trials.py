"""Aggregate trial outcomes and evaluation reports offline."""

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]

OUTCOMES = {
    "completed",
    "step_limit",
    "stopped",
    "failed",
}


def read_json(path):
    return json.loads(Path(path).read_text())


def nonnegative_int(report, field):
    value = report.get(field)
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid or missing metric: {field}")
    return value


def aggregate(plan_path, root=ROOT):
    plan = read_json(plan_path)
    trials = plan.get("trials", [])

    if plan.get("dry_run") is not False:
        raise ValueError("Expected an executed experiment plan.")

    if not trials or len(trials) != plan.get("sample_count"):
        raise ValueError("Trial count does not match the plan.")

    ids = [trial["trial_id"] for trial in trials]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate trial IDs.")

    def resolve(path):
        path = Path(path)
        return path if path.is_absolute() else Path(root) / path

    outcomes = Counter()
    rows = []
    steps = []
    tokens = []
    reports_seen = 0
    completed_games = 0
    attempts = 0
    accepted = 0
    errors = 0
    unknown = 0

    for trial in trials:
        trial_id = trial["trial_id"]
        report_path = resolve(trial["report"])
        status_path = report_path.with_name(
            f"{trial_id}-status.json"
        )

        if not status_path.is_file():
            if report_path.exists():
                raise ValueError(
                    f"{trial_id}: report exists without status."
                )
            outcomes["missing_status"] += 1
            rows.append({
                "trial_id": trial_id,
                "outcome": "missing_status",
                "has_report": False,
            })
            continue

        status = read_json(status_path)
        if status.get("trial_id") != trial_id:
            raise ValueError(f"{trial_id}: status ID mismatch.")

        outcome = status.get("outcome")
        if outcome not in OUTCOMES:
            raise ValueError(f"{trial_id}: unknown outcome.")

        outcomes[outcome] += 1

        has_report = report_path.is_file()
        if has_report != (status.get("report_written") is True):
            raise ValueError(
                f"{trial_id}: status/report inconsistency."
            )

        row = {
            "trial_id": trial_id,
            "outcome": outcome,
            "has_report": has_report,
        }

        if has_report:
            report = read_json(report_path)
            reports_seen += 1

            step_count = nonnegative_int(
                report, "model_steps"
            )
            attempt_count = nonnegative_int(
                report, "play_move_attempts"
            )
            accepted_count = nonnegative_int(
                report, "accepted_moves"
            )
            error_count = nonnegative_int(
                report, "tool_errors"
            )
            unknown_count = nonnegative_int(
                report, "unknown_outcomes"
            )

            if (
                accepted_count + error_count + unknown_count
                != attempt_count
            ):
                raise ValueError(
                    f"{trial_id}: move outcome counts do not add up."
                )

            usage = report.get("recorded_action_tokens")
            if usage is not None:
                if type(usage) is not int or usage < 0:
                    raise ValueError(
                        f"{trial_id}: invalid token usage."
                    )
                tokens.append(usage)

            game_over = report.get("game_over")
            if game_over is not None and type(game_over) is not bool:
                raise ValueError(
                    f"{trial_id}: invalid game_over value."
                )

            completed_games += game_over is True
            steps.append(step_count)
            attempts += attempt_count
            accepted += accepted_count
            errors += error_count
            unknown += unknown_count

            row.update({
                "model_steps": step_count,
                "recorded_action_tokens": usage,
                "game_over": game_over,
            })

        rows.append(row)

    return {
        "experiment_id": plan["experiment_id"],
        "model": plan["model"],
        "harness_commit": plan["harness_commit"],
        "planned_trials": len(trials),
        "reports_available": reports_seen,
        "report_coverage": reports_seen / len(trials),
        "outcomes": dict(sorted(outcomes.items())),
        "summary": {
            "mean_model_steps": (
                mean(steps) if steps else None
            ),
            "total_play_move_attempts": attempts,
            "total_accepted_moves": accepted,
            "total_tool_errors": errors,
            "total_unknown_outcomes": unknown,
            "observed_move_acceptance_rate": (
                accepted / attempts if attempts else None
            ),
            "completed_games": completed_games,
            "observed_game_completion_rate": (
                completed_games / reports_seen
                if reports_seen else None
            ),
            "mean_recorded_action_tokens": (
                mean(tokens) if tokens else None
            ),
            "token_usage_reports": len(tokens),
        },
        "trials": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()

    print(json.dumps(aggregate(args.plan), indent=2))


if __name__ == "__main__":
    main()
