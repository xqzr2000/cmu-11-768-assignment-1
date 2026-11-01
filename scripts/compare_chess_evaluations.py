"""Compare two offline chess evaluation reports."""

import json
import sys
from pathlib import Path


METRICS = (
    "model_steps",
    "play_move_attempts",
    "accepted_moves",
    "tool_errors",
    "unknown_outcomes",
    "recorded_action_tokens",
    "compactions",
)

CONFIG_FIELDS = (
    "model",
    "environment",
    "step_limit",
    "sample_count",
)


def load_experiment(path):
    data = json.loads(Path(path).read_text())

    # Accept a full experiment record or a raw evaluation.
    report = data.get("evaluation", data)

    return data, report


def summarize(report):
    metrics = {
        name: report.get(name)
        for name in METRICS
    }

    attempts = metrics["play_move_attempts"]
    steps = metrics["model_steps"]
    tokens = metrics["recorded_action_tokens"]

    metrics["move_acceptance_rate"] = (
        metrics["accepted_moves"] / attempts
        if isinstance(attempts, int)
        and attempts > 0
        and isinstance(metrics["accepted_moves"], int)
        else None
    )

    metrics["tokens_per_step"] = (
        tokens / steps
        if isinstance(tokens, (int, float))
        and isinstance(steps, int)
        and steps > 0
        else None
    )

    metrics["game_over"] = report.get("game_over")

    return metrics


def compare(baseline_path, candidate_path):
    baseline_data, baseline_report = load_experiment(
        baseline_path
    )
    candidate_data, candidate_report = load_experiment(
        candidate_path
    )

    baseline = summarize(baseline_report)
    candidate = summarize(candidate_report)

    comparison = {}

    for metric in baseline:
        old = baseline[metric]
        new = candidate[metric]

        delta = (
            new - old
            if type(old) in (int, float)
            and type(new) in (int, float)
            else None
        )

        comparison[metric] = {
            "baseline": old,
            "candidate": new,
            "delta": delta,
        }

    mismatches = {}

    for field in CONFIG_FIELDS:
        old = baseline_data.get(field)
        new = candidate_data.get(field)

        if old is not None and new is not None and old != new:
            mismatches[field] = {
                "baseline": old,
                "candidate": new,
            }

    warnings = []

    if mismatches:
        warnings.append(
            "Experimental configurations differ."
        )

    if (
        baseline_data.get("sample_count") == 1
        or candidate_data.get("sample_count") == 1
    ):
        warnings.append(
            "Single-run results cannot establish "
            "a reliable performance improvement."
        )

    return {
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "metrics": comparison,
        "configuration_mismatches": mismatches,
        "warnings": warnings,
    }


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: compare_chess_evaluations.py "
            "BASELINE CANDIDATE OUTPUT"
        )

    result = compare(sys.argv[1], sys.argv[2])

    output = Path(sys.argv[3])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2) + "\n"
    )

    print(json.dumps(result, indent=2))
