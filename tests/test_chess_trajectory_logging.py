"""Offline tests for preserving final chess tool observations."""

import copy
import json
import sys
from pathlib import Path

import pytest

import assignment.cli as cli
from assignment.agent.base import StepLimitError


def call(call_id):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "play_move",
            "arguments": '{"move":"e2e4"}',
        },
    }


def run_mock_chess(monkeypatch, tmp_path, history, *, step_limit=False):
    """Exercise the real CLI with fake chess and model execution."""

    patch = tmp_path / "server.patch"
    patch.write_text("mock patch")

    trajectory = tmp_path / "trajectory.json"
    result = tmp_path / "result.json"

    class FakeSandbox:
        server_url = "http://localhost:9999"

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeAgent:
        def __init__(self, **kwargs):
            self.logs_save_path = kwargs["logs_save_path"]
            self.history = copy.deepcopy(history)
            self.last_state = {
                "game_over": True,
                "status": "Checkmate",
            }
            self.steps_taken = 2
            self.api_responses = [
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": next(
                                    (
                                        m.get("tool_calls", [])
                                        for m in reversed(history)
                                        if m["role"] == "assistant"
                                    ),
                                    [],
                                )
                            }
                        }
                    ]
                }
            ]

        def run(self):
            # Simulate the existing protected Agent.run() saver.
            Path(self.logs_save_path).write_text(
                json.dumps({
                    "prompts": [["mock prompt"]],
                    "responses": self.api_responses,
                    "compactions": [],
                })
            )

            if step_limit:
                raise StepLimitError("Mock step limit reached")

    monkeypatch.setattr(cli, "ChessSandbox", FakeSandbox)
    monkeypatch.setattr(cli, "ChessAgent", FakeAgent)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "assignment-play-chess",
            "--model", "mock-model",
            "--patch", str(patch),
            "--trajectory", str(trajectory),
            "--result", str(result),
        ],
    )

    if step_limit:
        with pytest.raises(StepLimitError):
            cli.run_chess_agent()
    else:
        cli.run_chess_agent()

    return json.loads(trajectory.read_text()), result


def test_step_limit_preserves_final_observations(monkeypatch, tmp_path):
    history = [
        {"role": "assistant", "tool_calls": [call("reused")]},
        {
            "role": "tool",
            "tool_call_id": "reused",
            "content": "Old observation",
        },
        {
            "role": "assistant",
            "tool_calls": [call("reused"), call("second")],
        },
        {
            "role": "tool",
            "tool_call_id": "reused",
            "content": "Final observation one",
        },
        {
            "role": "tool",
            "tool_call_id": "second",
            "content": "Final observation two",
        },
    ]

    data, _ = run_mock_chess(
        monkeypatch, tmp_path, history, step_limit=True
    )

    assert data["final_observations"] == history[-2:]


def test_text_only_step_has_no_final_observations(monkeypatch, tmp_path):
    history = [
        {"role": "assistant", "tool_calls": [call("old")]},
        {
            "role": "tool",
            "tool_call_id": "old",
            "content": "Old observation",
        },
        {"role": "assistant", "content": "Thinking"},
        {"role": "user", "content": "Please call a tool"},
    ]

    data, _ = run_mock_chess(
        monkeypatch, tmp_path, history, step_limit=True
    )

    assert data["final_observations"] == []


def test_completed_game_preserves_existing_outputs(monkeypatch, tmp_path):
    history = [
        {"role": "assistant", "tool_calls": [call("final")]},
        {
            "role": "tool",
            "tool_call_id": "final",
            "content": "Game over",
        },
    ]

    data, result = run_mock_chess(
        monkeypatch, tmp_path, history
    )

    assert "prompts" in data
    assert "responses" in data
    assert "compactions" in data
    assert result.is_file()
    assert json.loads(result.read_text())["game_over"] is True
