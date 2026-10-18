"""Regression tests for chess tool-call ordering."""

from unittest.mock import patch

import pytest

import assignment.agent.chess_agent as chess_module
from assignment.agent.chess_agent import ChessAgent
from assignment.agent.tools import (
    PLAY_MOVE_TOOL,
    RUN_PYTHON_TOOL,
    SIMULATE_MOVE_TOOL,
)


def call(name, call_id):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": "{}",
        },
    }


@pytest.fixture
def agent(monkeypatch):
    # Only test the tool dispatcher, without an API call.
    agent = ChessAgent.__new__(ChessAgent)
    agent.tools = [
        PLAY_MOVE_TOOL,
        RUN_PYTHON_TOOL,
        SIMULATE_MOVE_TOOL,
    ]
    agent.finished = False
    agent.chess_client = object()

    monkeypatch.setattr(agent, "_play", lambda args: "played")
    monkeypatch.setattr(
        agent, "_run_python", lambda args: "python executed"
    )

    return agent


@pytest.mark.parametrize("changing_tool", [
    "play_move",
    "run_python",
])
def test_simulation_rejected_after_board_change(agent, changing_tool):
    with patch.object(
        chess_module, "_simulate_move", return_value="simulated"
    ) as simulate:
        messages = agent.execute_tool_calls([
            call(changing_tool, "change_1"),
            call("simulate_move", "sim_2"),
        ])

    assert messages[1]["tool_call_id"] == "sim_2"
    assert "<chess_error>" in messages[1]["content"]
    assert "stale" in messages[1]["content"]
    simulate.assert_not_called()


def test_simulations_allowed_before_board_change(agent):
    with patch.object(
        chess_module, "_simulate_move", return_value="simulated"
    ) as simulate:
        messages = agent.execute_tool_calls([
            call("simulate_move", "sim_1"),
            call("simulate_move", "sim_2"),
            call("play_move", "move_3"),
        ])

    assert simulate.call_count == 2
    assert messages[0]["content"] == "simulated"
    assert messages[1]["content"] == "simulated"
    assert messages[2]["content"] == "played"


def test_guard_resets_on_next_response(agent):
    with patch.object(
        chess_module, "_simulate_move", return_value="simulated"
    ) as simulate:
        agent.execute_tool_calls([call("play_move", "move_1")])
        messages = agent.execute_tool_calls([
            call("simulate_move", "sim_2")
        ])

    assert messages[0]["content"] == "simulated"
    simulate.assert_called_once()
