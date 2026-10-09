"""Tabulate the Part 3 observation A/B experiment from saved trajectories.

Offline and free. For each of the four runs it counts ``play_move`` calls,
calls the server rejected as illegal, other invalid calls, the invalid-move
rate, and whether the game reached ``game_over: true``, then writes
``artifacts/observation-experiment.md``. Review and edit the prose before
submitting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RUNS = [
    ("DeepSeek", "board only", "part3-no-legal-moves-deepseek"),
    ("DeepSeek", "board + legal moves", "part3-legal-moves-deepseek"),
    ("gpt-oss", "board only", "part3-no-legal-moves-gpt-oss"),
    ("gpt-oss", "board + legal moves", "part3-legal-moves-gpt-oss"),
]


def _message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or [{}]
    return choices[0].get("message") or {}


def _observations(prompts: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """The longest prompt holds every observation except the final action's."""

    return max(prompts, key=len) if prompts else []


def analyze(trajectory: Path, result: Path) -> dict[str, Any]:
    data = json.loads(trajectory.read_text())
    responses = data.get("responses", [])
    history = _observations(data.get("prompts", []))
    final_state = json.loads(result.read_text()) if result.is_file() else {}

    # Walk the history: for each assistant action, match its calls to the tool
    # messages that follow it (IDs are only unique within one action).
    outcomes: list[str] = []
    for index, message in enumerate(history):
        if message.get("role") != "assistant":
            continue
        following = []
        for later in history[index + 1:]:
            if later.get("role") != "tool":
                break
            following.append(later)
        for call in message.get("tool_calls") or []:
            if (call.get("function") or {}).get("name") != "play_move":
                continue
            reply = next((m for m in following if m.get("tool_call_id") == call.get("id")), None)
            if reply is not None:
                following.remove(reply)
            outcomes.append(_classify(reply.get("content", "") if reply else None))

    # The final action's observations never reach another prompt, so infer the
    # outcome of its first play_move from the saved final state; any further
    # play_move in the same response is rejected by the harness.
    if responses:
        last_calls = [
            c for c in _message(responses[-1]).get("tool_calls") or []
            if (c.get("function") or {}).get("name") == "play_move"
        ]
        if last_calls:
            try:
                move = json.loads(last_calls[0]["function"].get("arguments") or "{}").get("move")
            except (json.JSONDecodeError, AttributeError):
                move = None
            played = move is not None and final_state.get("human_move") == move
            outcomes.append("legal" if played else "unknown")
            outcomes.extend("invalid" for _ in last_calls[1:])

    calls = len(outcomes)
    illegal = outcomes.count("illegal")
    invalid = outcomes.count("invalid")
    return {
        "steps": len(responses),
        "calls": calls,
        "illegal": illegal,
        "invalid_other": invalid,
        "unknown": outcomes.count("unknown"),
        "rate": (illegal + invalid) / calls if calls else 0.0,
        "game_over": bool(final_state.get("game_over")),
        "status": final_state.get("status", "(no result file)"),
        "plies": len(final_state.get("history", []) or []),
    }


def _classify(content: str | None) -> str:
    if content is None:
        return "unknown"
    if not content.startswith("<chess_error>"):
        return "legal"
    if "server rejected" in content:
        return "illegal"
    return "invalid"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/observation-experiment.md"))
    args = parser.parse_args()

    rows, results = [], {}
    for model, condition, stem in RUNS:
        trajectory = args.artifacts / f"{stem}.json"
        result = args.artifacts / f"{stem}-result.json"
        if not trajectory.is_file():
            print(f"missing {trajectory}; skipping")
            continue
        r = analyze(trajectory, result)
        results[(model, condition)] = r
        rows.append(
            f"| {model} | {condition} | {r['calls']} | {r['illegal']} | "
            f"{r['invalid_other']} | {r['rate'] * 100:.1f}% | "
            f"{'yes' if r['game_over'] else 'no'} | {r['status']} | {r['plies']} | {r['steps']} |"
        )
    if not rows:
        raise SystemExit("No experiment trajectories found in artifacts/.")

    findings = []
    for model in ("DeepSeek", "gpt-oss"):
        a = results.get((model, "board only"))
        b = results.get((model, "board + legal moves"))
        if a and b:
            findings.append(
                f"- **{model}:** invalid-move rate {a['rate'] * 100:.1f}% with the board "
                f"only vs {b['rate'] * 100:.1f}% with legal moves listed; "
                f"game over: {'yes' if a['game_over'] else 'no'} vs "
                f"{'yes' if b['game_over'] else 'no'}."
            )

    report = f"""# Observation A/B experiment: board only vs. board + legal moves

Each run plays White against the server's deterministic Black bot through
`play_move`. The only difference between conditions is whether observations
(and the system prompt) include the `legal_moves` list; the board diagram, FEN,
and recent history are always shown.

"Rejected as illegal" counts `play_move` calls the chess server refused.
"Other invalid" counts calls that failed before reaching the server (malformed
arguments, or a second move in one response). Invalid-move rate = (illegal +
other invalid) / total `play_move` calls.

| Model | Observation | `play_move` calls | Rejected as illegal | Other invalid | Invalid-move rate | `game_over: true` | Final status | Plies played | ReAct steps |
|---|---|---:|---:|---:|---:|---|---|---:|---:|
{chr(10).join(rows)}

## Findings

{chr(10).join(findings) or '- (add both conditions for a model to compare them)'}

## Interpretation

With legal moves listed, choosing a valid action reduces to selecting a string
from the observation, so illegal moves should be rare and the game can proceed
to a terminal state within the step budget. With only the board and FEN, the
model must infer legality itself — tracking pins, checks, castling rights, en
passant, and promotion syntax — and each mistake costs a step, so errors
compound as the position gets more complex (especially when in check, where
most pseudo-legal moves are illegal). Comparing the two models shows how much
of this depends on the model's own board-state reasoning versus on the tool
interface doing that work for it. Single games are noisy, so treat these as
indicative rather than conclusive.

_Edit this section with what you actually observed in the trajectories (e.g.
which kinds of illegal moves occurred and when)._
"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(f"Wrote {args.output}. Review the prose before submitting.")


if __name__ == "__main__":
    main()
