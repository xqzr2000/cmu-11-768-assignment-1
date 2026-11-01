"""Minimal offline evaluator for chess-agent trajectories."""

import json
import re
import sys
from pathlib import Path


def evaluate(trajectory_path, result_path):
    trajectory = json.loads(Path(trajectory_path).read_text())
    result = json.loads(Path(result_path).read_text())

    responses = trajectory["responses"]
    prompts = trajectory["prompts"]

    def observation_for(step, call_id):
        if step + 1 < len(prompts):
            messages = prompts[step + 1]
        else:
            messages = trajectory.get("final_observations", [])

        for message in reversed(messages):
            if (
                isinstance(message, dict)
                and message.get("role") == "tool"
                and message.get("tool_call_id") == call_id
            ):
                return str(message.get("content") or "")
        return None

    accepted = 0
    errors = 0
    unknown = 0
    attempts = 0
    moves = []

    for step, response in enumerate(responses):
        choices = response.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}

        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            if fn.get("name") != "play_move":
                continue

            attempts += 1
            try:
                args = json.loads(fn.get("arguments") or "{}")
                move = args.get("move")
            except (ValueError, AttributeError):
                move = None

            obs = observation_for(step, call.get("id"))

            if obs is None:
                outcome = "unknown"
                unknown += 1
            elif "<chess_error>" in obs:
                outcome = "error"
                errors += 1
            elif (
                "<chess_state>" in obs
                and move is not None
                and re.search(
                    rf"(?m)^human_move:\s*{re.escape(str(move))}\s*$",
                    obs,
                )
            ):
                outcome = "accepted"
                accepted += 1
            else:
                outcome = "unknown"
                unknown += 1

            moves.append({
                "step": step + 1,
                "move": move,
                "outcome": outcome,
            })

    usage = [
        (response.get("usage") or {}).get("total_tokens")
        for response in responses
    ]

    return {
        "model_steps": len(responses),
        "play_move_attempts": attempts,
        "accepted_moves": accepted,
        "tool_errors": errors,
        "unknown_outcomes": unknown,
        "recorded_action_tokens": (
            sum(usage)
            if all(isinstance(value, int) for value in usage)
            else None
        ),
        "compactions": len(trajectory.get("compactions", [])),
        "game_over": result.get("game_over"),
        "final_fen": result.get("fen"),
        "moves": moves,
    }


if __name__ == "__main__":
    trajectory_file = sys.argv[1]
    result_file = sys.argv[2]
    output_file = Path(sys.argv[3])

    report = evaluate(trajectory_file, result_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
