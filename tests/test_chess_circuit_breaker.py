"""Offline tests: ChessAgent stops when the chess server is gone, not on ordinary mistakes."""

from __future__ import annotations

import json

import httpx
import pytest

from assignment.agent import Agent, ChessAgent, ChessServerUnreachableError
from assignment.cli import _write_game_result

STATE = {
    "status": "Your turn", "turn": "white", "in_check": False, "game_over": False,
    "fen": "fen-1", "squares": {"e1": "K", "e8": "k"}, "history": [],
    "legal_moves": ["e1e2"], "human_move": None, "engine_move": None,
}


class FakeEnvironment:
    cwd = "/testbed"
    server_url = "http://chess.test"
    system, release, version, machine = "Linux", "6.1", "#1", "x86_64"

    def stop(self):
        pass


class Server:
    """Mock chess API; flip ``down`` (everything) or ``moves_down`` (only /api/move)."""

    def __init__(self):
        self.down = False
        self.moves_down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down or (self.moves_down and request.url.path == "/api/move"):
            raise httpx.ConnectError("[Errno 111] Connection refused", request=request)
        if request.url.path in ("/api/reset", "/api/state"):
            return httpx.Response(200, json=STATE)
        if request.url.path == "/api/move":
            if json.loads(request.content) == {"move": "e1e2"}:
                return httpx.Response(200, json={**STATE, "fen": "fen-2"})
            return httpx.Response(400, json={"detail": "illegal move"})
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
def server():
    return Server()


@pytest.fixture
def agent(monkeypatch, server, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://model.test/v1")
    client = httpx.Client(base_url="http://chess.test", transport=httpx.MockTransport(server.handler))
    return ChessAgent(FakeEnvironment(), model="test-model", http_client=client,
                      auto_stop_environment=False, logs_save_path=str(tmp_path / "traj.json"))


def move(uci: str, call_id: str = "c1") -> dict:
    return {"id": call_id, "type": "function",
            "function": {"name": "play_move", "arguments": json.dumps({"move": uci})}}


def test_illegal_moves_never_trip_the_breaker(agent):
    for _ in range(10):
        out = agent.execute_tool_calls([move("a1a8")])
        assert "<chess_error>" in out[0]["content"]
    assert agent.unreachable_streak == 0 and agent.environment_lost is None


def test_dead_server_trips_after_three_steps_and_blocks_the_next_model_call(agent, server):
    server.down = True
    for step in range(1, 4):
        out = agent.execute_tool_calls([move("e1e2")])
        assert "Could not reach the chess server" in out[0]["content"]  # still returned as an observation
        assert agent.unreachable_streak == step
    assert agent.environment_lost and "3 consecutive steps" in agent.environment_lost
    with pytest.raises(ChessServerUnreachableError):
        agent.query_language_model()
    with pytest.raises(ChessServerUnreachableError):
        agent.maybe_compact_context()


def test_transient_failure_resets_the_streak(agent, server):
    server.down = True
    agent.execute_tool_calls([move("e1e2")])
    agent.execute_tool_calls([move("e1e2")])
    server.down = False
    agent.execute_tool_calls([move("e1e2")])
    assert agent.unreachable_streak == 0 and agent.environment_lost is None


def test_breaker_confirms_with_a_direct_state_read_before_stopping(agent, server):
    server.moves_down = True  # /api/move fails but /api/state still answers
    for _ in range(3):
        agent.execute_tool_calls([move("e1e2")])
    assert agent.environment_lost is None and agent.unreachable_streak == 0


def test_run_stops_early_and_keeps_the_failing_observation(agent, server, monkeypatch):
    calls = {"n": 0}

    def fake_query(self):
        calls["n"] += 1
        return {"role": "assistant", "content": None, "tool_calls": [move("e1e2", f"c{calls['n']}")]}

    monkeypatch.setattr(Agent, "query_language_model", fake_query)
    server.down = True
    with pytest.raises(ChessServerUnreachableError):
        agent.run()
    assert calls["n"] == 3, "no model call after the breaker trips"
    last = agent.history[-1]
    assert last["role"] == "tool" and "Could not reach the chess server" in last["content"]
    saved = json.loads(open(agent.logs_save_path).read())
    assert "responses" in saved  # provided logging still ran


def test_max_unreachable_steps_is_validated(monkeypatch, server):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://model.test/v1")
    client = httpx.Client(base_url="http://chess.test", transport=httpx.MockTransport(server.handler))
    with pytest.raises(ValueError):
        ChessAgent(FakeEnvironment(), model="m", http_client=client, max_unreachable_steps=0)


def test_game_result_is_written_even_when_the_run_stops_early(tmp_path):
    class Stub:
        last_state = {**STATE, "fen": "fen-57"}

    path = tmp_path / "game-result.json"
    _write_game_result(path, Stub(), ChessServerUnreachableError("gone"))
    data = json.loads(path.read_text())
    assert data["fen"] == "fen-57" and data["game_over"] is False
    assert data["run_stopped_early"] == "ChessServerUnreachableError: gone"
    _write_game_result(path, Stub(), None)
    assert "run_stopped_early" not in json.loads(path.read_text())


def test_programmatic_skill_agent_registers_each_tool_once(monkeypatch, server):
    """Regression: base Agent and ChessAgent both added invoke_skill (HTTP 400 'Tool names must be unique')."""
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://model.test/v1")
    client = httpx.Client(base_url="http://chess.test", transport=httpx.MockTransport(server.handler))
    agent = ChessAgent(FakeEnvironment(), model="m", http_client=client, auto_stop_environment=False,
                       programmatic_tools=True, skills_path="tasks/chess-skills")
    names = [tool["function"]["name"] for tool in agent.tools]
    assert len(names) == len(set(names)), names
    assert set(names) == {"invoke_skill", "play_move", "simulate_move", "run_python"}
