"""Offline regression tests for chess trajectory evaluation."""

import json
from pathlib import Path
from runpy import run_path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "eval_chess_trajectory.py"
)
evaluate = run_path(str(SCRIPT))["evaluate"]


def make_response(move="e2e4", call_id="call_1", tokens=100):
    return {
        "choices": [{
            "message": {
                "tool_calls": [{
                    "id": call_id,
                    "function": {
                        "name": "play_move",
                        "arguments": json.dumps({"move": move}),
                    },
                }]
            }
        }],
        "usage": {"total_tokens": tokens},
    }


def run_evaluation(tmp_path, trajectory, result=None):
    trajectory_file = tmp_path / "trajectory.json"
    result_file = tmp_path / "result.json"

    trajectory_file.write_text(json.dumps(trajectory))
    result_file.write_text(json.dumps(result or {"game_over": False}))

    return evaluate(trajectory_file, result_file)


@pytest.mark.parametrize(
    "observation,outcome",
    [
        ("<chess_state>\nhuman_move: e2e4\n", "accepted"),
        ("<chess_error>Illegal move</chess_error>", "error"),
        ("<chess_state>\nhuman_move: d2d4\n", "unknown"),
        (None, "unknown"),
    ],
)
def test_move_outcomes(tmp_path, observation, outcome):
    trajectory = {
        "prompts": [[]],
        "responses": [make_response()],
        "compactions": [],
        "final_observations": (
            [{
                "role": "tool",
                "tool_call_id": "call_1",
                "content": observation,
            }]
            if observation is not None else []
        ),
    }

    report = run_evaluation(tmp_path, trajectory)

    assert report["play_move_attempts"] == 1
    assert report["moves"][0]["outcome"] == outcome
    assert report["accepted_moves"] == int(outcome == "accepted")
    assert report["tool_errors"] == int(outcome == "error")
    assert report["unknown_outcomes"] == int(outcome == "unknown")


def test_observations_across_steps(tmp_path):
    trajectory = {
        "prompts": [
            [],
            [{
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "<chess_state>\nhuman_move: e2e4\n",
            }],
        ],
        "responses": [
            make_response("e2e4", "call_1", 100),
            make_response("g1f3", "call_2", 200),
        ],
        "compactions": [],
        "final_observations": [{
            "role": "tool",
            "tool_call_id": "call_2",
            "content": "<chess_state>\nhuman_move: g1f3\n",
        }],
    }

    report = run_evaluation(tmp_path, trajectory)

    assert report["model_steps"] == 2
    assert report["accepted_moves"] == 2
    assert report["recorded_action_tokens"] == 300
    assert report["unknown_outcomes"] == 0


def test_missing_token_usage(tmp_path):
    response = make_response()
    response.pop("usage")

    trajectory = {
        "prompts": [[]],
        "responses": [response],
        "compactions": [],
        "final_observations": [],
    }

    report = run_evaluation(tmp_path, trajectory)

    assert report["recorded_action_tokens"] is None
    assert report["unknown_outcomes"] == 1
