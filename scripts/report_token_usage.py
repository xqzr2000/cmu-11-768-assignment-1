"""Compare token usage of a compacted run against a full-context baseline.

Offline and free: reads saved trajectories and writes
``artifacts/token-usage-analysis.md`` with measured numbers and a first-pass
reading of them. Review and edit the prose before submitting.

    uv run python scripts/report_token_usage.py \
        --compacted artifacts/django__django-15368-trajectory.json \
        --baseline artifacts/django__django-15368-baseline-trajectory.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

INSTANCE = "django__django-15368"


def _usage(response: dict[str, Any]) -> dict[str, int]:
    usage = response.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    return {
        "prompt": int(usage.get("prompt_tokens") or 0),
        "completion": int(usage.get("completion_tokens") or 0),
        "cached": int(details.get("cached_tokens") or 0),
    }


def summarize(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    responses = data.get("responses", [])
    compactions = data.get("compactions", [])
    actions = [_usage(r) for r in responses]
    summaries = [_usage(c.get("compaction_response") or {}) for c in compactions]
    prompt_series = [u["prompt"] for u in actions]

    action_prompt = sum(u["prompt"] for u in actions)
    action_completion = sum(u["completion"] for u in actions)
    compaction_prompt = sum(u["prompt"] for u in summaries)
    compaction_completion = sum(u["completion"] for u in summaries)
    return {
        "path": str(path),
        "steps": len(responses),
        "prompt_series": prompt_series,
        "action_prompt": action_prompt,
        "action_completion": action_completion,
        "cached": sum(u["cached"] for u in actions + summaries),
        "peak_prompt": max(prompt_series, default=0),
        "mean_prompt": round(mean(prompt_series)) if prompt_series else 0,
        "final_prompt": prompt_series[-1] if prompt_series else 0,
        "compactions": len(compactions),
        "compaction_prompt": compaction_prompt,
        "compaction_completion": compaction_completion,
        "total": action_prompt + action_completion + compaction_prompt + compaction_completion,
        "events": [
            {
                "step": c.get("step"),
                "before": c.get("estimated_tokens_before"),
                "after": c.get("estimated_tokens_after"),
            }
            for c in compactions
        ],
    }


def _pct(new: float, old: float) -> str:
    if not old:
        return "n/a"
    return f"{(new - old) / old * 100:+.1f}%"


def _series_rows(a: list[int], b: list[int]) -> str:
    rows = ["| Step | Compacted prompt tokens | Baseline prompt tokens |", "|---:|---:|---:|"]
    for i in range(max(len(a), len(b))):
        left = f"{a[i]:,}" if i < len(a) else ""
        right = f"{b[i]:,}" if i < len(b) else ""
        rows.append(f"| {i + 1} | {left} | {right} |")
    return "\n".join(rows)


def render(c: dict[str, Any], b: dict[str, Any], threshold: int) -> str:
    metrics = [
        ("ReAct steps (action requests)", "steps"),
        ("Prompt tokens, action requests", "action_prompt"),
        ("Completion tokens, action requests", "action_completion"),
        ("Compaction requests", "compactions"),
        ("Prompt tokens, compaction requests", "compaction_prompt"),
        ("Completion tokens, compaction requests", "compaction_completion"),
        ("**Total tokens billed**", "total"),
        ("Peak prompt size (one request)", "peak_prompt"),
        ("Mean prompt size per request", "mean_prompt"),
        ("Final prompt size", "final_prompt"),
        ("Cached prompt tokens reported", "cached"),
    ]
    table = ["| Metric | Compacted | Full context | Change |", "|---|---:|---:|---:|"]
    for label, key in metrics:
        table.append(f"| {label} | {c[key]:,} | {b[key]:,} | {_pct(c[key], b[key])} |")

    events = ["| Compaction | At step | Est. tokens before | Est. tokens after | Reduction |",
              "|---:|---:|---:|---:|---:|"]
    for i, e in enumerate(c["events"], 1):
        before, after = e["before"] or 0, e["after"] or 0
        events.append(
            f"| {i} | {e['step']} | {before:,} | {after:,} | {_pct(after, before)} |"
        )

    observations = []
    if c["compactions"]:
        reductions = [
            (e["before"] - e["after"]) / e["before"]
            for e in c["events"]
            if e["before"] and e["after"] is not None
        ]
        observations.append(
            f"- Compaction fired {c['compactions']} time(s) at a {threshold:,}-token "
            f"threshold, cutting the estimated active prompt by "
            f"{mean(reductions) * 100:.0f}% on average per event."
        )
    else:
        observations.append("- **No compaction fired in the compacted run** — rerun it; the grade requires at least one.")
    observations.append(
        f"- Peak prompt size was {c['peak_prompt']:,} tokens with compaction vs "
        f"{b['peak_prompt']:,} without ({_pct(c['peak_prompt'], b['peak_prompt'])}); "
        f"mean prompt size {c['mean_prompt']:,} vs {b['mean_prompt']:,} "
        f"({_pct(c['mean_prompt'], b['mean_prompt'])})."
    )
    observations.append(
        f"- Summarization itself cost {c['compaction_prompt'] + c['compaction_completion']:,} "
        f"tokens ({c['compaction_prompt']:,} in, {c['compaction_completion']:,} out); "
        f"total billed tokens changed by {_pct(c['total'], b['total'])} "
        f"({c['total']:,} vs {b['total']:,})."
    )
    observations.append(
        f"- The runs took {c['steps']} vs {b['steps']} action steps. Generation is "
        "stochastic, so step counts from single runs are only indicative."
    )

    return f"""# Token usage: context compaction vs. full context ({INSTANCE})

Runs compared (both solved with the same harness and model; only the compaction
flag differs):

- Compacted (`COMPACT_THRESHOLD={threshold}`): `{c['path']}`
- Full context (`COMPACT_THRESHOLD=0`): `{b['path']}`

Token counts are the provider-reported `usage` of every request, including the
extra summarization requests that compaction makes. "Estimated" figures come
from the harness's character-based estimate at compaction time.

## Summary

{chr(10).join(table)}

## Compaction events

{chr(10).join(events) if c['events'] else '_None._'}

## Observations

{chr(10).join(observations)}

## Explanation of the trends

In a ReAct loop the whole history is resent on every request, so without
compaction each step's prompt is the previous prompt plus the newest action and
observation: prompt size grows roughly linearly with the step count, and the
cumulative prompt tokens billed grow roughly quadratically. Large observations
(file listings, test output) make each increment bigger.

With compaction, once the estimated prompt passes the threshold the older prefix
of the history is replaced by a short model-written working memory, while the
system prompt, the task, and the most recent complete action/observation step
stay verbatim. The prompt therefore drops back toward a floor of
*system + task + memory + latest step* and grows again until the next
compaction, giving the saw-tooth in the per-step table below instead of a
steady climb.

## Trade-offs

- **Cost and context headroom vs. extra calls.** Compaction lowers the size of
  every later request, which matters most for long runs, but each compaction is
  an extra model call that reads the old prefix. On a short run, or when the
  threshold is low enough that it fires nearly every step, that overhead can
  offset the savings.
- **Lossy memory.** The summary keeps what the summarizer judged important.
  Exact outputs, line numbers, or a detail that only matters later can be lost,
  which can lead the agent to re-read files or repeat commands, sometimes
  adding steps.
- **Cache effects.** Rewriting the prompt prefix invalidates provider prompt
  caching for that prefix, whereas a monotonically growing full-context prompt
  is cache-friendly; discounted cached tokens narrow the cost gap.
- **Focus.** A shorter prompt without stale tool output can help the model
  focus on the current state, while the full-context agent can always look
  back at the exact raw evidence.

<details>
<summary>Per-step prompt tokens</summary>

{_series_rows(c['prompt_series'], b['prompt_series'])}

</details>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--compacted", type=Path, default=Path(f"artifacts/{INSTANCE}-trajectory.json"))
    parser.add_argument("--baseline", type=Path, default=Path(f"artifacts/{INSTANCE}-baseline-trajectory.json"))
    parser.add_argument("--threshold", type=int, default=6000)
    parser.add_argument("--output", type=Path, default=Path("artifacts/token-usage-analysis.md"))
    args = parser.parse_args()

    missing = [p for p in (args.compacted, args.baseline) if not p.is_file()]
    if missing:
        raise SystemExit("Missing trajectory: " + ", ".join(map(str, missing)))

    report = render(summarize(args.compacted), summarize(args.baseline), args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(f"Wrote {args.output}. Review the prose before submitting.")


if __name__ == "__main__":
    main()
