"""The Part 3 chess agent: reuse the shared loop with one new domain tool."""

from __future__ import annotations

import json
from typing import Any

import httpx

from assignment.agent.base import (
    DEFAULT_COMPACTION_KEEP_RECENT_STEPS,
    DEFAULT_COMPACTION_MAX_TOKENS,
    Agent,
)
from assignment.agent.chess_tools import (
    SERVER_UNREACHABLE,
    _chess_error,
    _game_state,
    _invoke_skill,
    _play_move,
    CHESS_PORT,
    _run_python,
    _simulate_move,
)
from assignment.agent.tools import (
    INVOKE_SKILL_TOOL,
    PLAY_MOVE_TOOL,
    RUN_PYTHON_TOOL,
    SIMULATE_MOVE_TOOL,
)
from assignment.prompts import (
    CHESS_AGENT_NO_LEGAL_MOVES_PROMPT_TEMPLATE,
    CHESS_AGENT_SYSTEM_PROMPT_TEMPLATE,
    PROGRAMMATIC_CHESS_PROMPT,
)
from assignment.env import Environment


DEFAULT_MAX_UNREACHABLE_STEPS = 3
_LIVE_BOARD_LOST = "Could not re-read the live board"


class ChessServerUnreachableError(RuntimeError):
    """The chess environment is gone; further model calls cannot help."""


def format_chess_state(
    state: dict[str, Any], *, include_legal_moves: bool = True
) -> str:
    """Turn chess API JSON into a compact observation an LLM can act on."""

    squares = state.get("squares", {})
    board_lines = ["    a b c d e f g h"]
    for rank in range(8, 0, -1):
        pieces = [squares.get(f"{file}{rank}", ".") for file in "abcdefgh"]
        board_lines.append(f"{rank} | {' '.join(pieces)} | {rank}")
    board_lines.append("    a b c d e f g h")

    recent_history = state.get("history", [])[-8:]
    history = (
        " ".join(
            f"{item.get('ply', '?')}:{item.get('san', '?')}" for item in recent_history
        )
        or "(none)"
    )
    legal_moves = " ".join(state.get("legal_moves", [])) or "(none)"
    board_text = "\n".join(board_lines)

    observation = (
        "<chess_state>\n"
        f"status: {state.get('status', 'unknown')}\n"
        f"turn: {state.get('turn', 'unknown')}\n"
        f"in_check: {state.get('in_check', False)}\n"
        f"game_over: {state.get('game_over', False)}\n"
        f"fen: {state.get('fen', '')}\n"
        f"human_move: {state.get('human_move') or '(none)'}\n"
        f"engine_move: {state.get('engine_move') or '(none)'}\n"
        "board:\n"
        f"{board_text}\n"
        f"recent_history: {history}\n"
    )
    if include_legal_moves:
        observation += f"legal_moves: {legal_moves}\n"
    return observation + "</chess_state>"


class ChessAgent(Agent):
    """An agent that plays White against the server's deterministic Black bot."""

    def __init__(
        self,
        environment: Environment,
        model: str | None = None,
        logs_save_path: str | None = None,
        step_limit: int = 200,
        skills_path: str | None = None,
        auto_stop_environment: bool = True,
        http_client: Any | None = None,
        reset_game: bool = True,
        compact_threshold_tokens: int | None = None,
        compaction_keep_recent_steps: int = None,
        compaction_max_tokens: int = None,
        programmatic_tools: bool = False,
        python_sandbox_port: int = CHESS_PORT,
        include_legal_moves: bool = True,
        max_unreachable_steps: int = DEFAULT_MAX_UNREACHABLE_STEPS,
    ):
        super().__init__(
            environment=environment,
            model=model,
            logs_save_path=logs_save_path,
            step_limit=step_limit,
            skills_path=skills_path,
            auto_stop_environment=auto_stop_environment,
            compact_threshold_tokens=compact_threshold_tokens,
            compaction_keep_recent_steps=compaction_keep_recent_steps,
            compaction_max_tokens=compaction_max_tokens,
        )

        self.tools.append(PLAY_MOVE_TOOL)

        if programmatic_tools:
            self.tools.append(SIMULATE_MOVE_TOOL)
            self.tools.append(RUN_PYTHON_TOOL)
        # The base Agent already registers invoke_skill when skills are loaded;
        # adding it again sends a duplicate tool name, which providers reject.
        if self.skills and INVOKE_SKILL_TOOL not in self.tools:
            self.tools.append(INVOKE_SKILL_TOOL)
        # run_python always executes in the sandbox, on the port the chess
        # server is listening on there.
        self.python_sandbox_port = python_sandbox_port
        self.include_legal_moves = include_legal_moves
        # Circuit breaker: an illegal move is the model's mistake and goes back
        # to it as a recoverable error, but a server that stops answering is
        # an environment failure no amount of retrying fixes. After this many
        # consecutive steps where every board call failed to connect, the run
        # stops instead of re-sending the whole game to the model each step.
        if max_unreachable_steps < 1:
            raise ValueError("max_unreachable_steps must be at least 1")
        self.max_unreachable_steps = max_unreachable_steps
        self.unreachable_streak = 0
        self.environment_lost: str | None = None

        if http_client is None:
            server_url = getattr(environment, "server_url", "")
            if not server_url:
                raise ValueError(
                    "ChessAgent needs an environment with server_url or an http_client."
                )
            http_client = httpx.Client(base_url=server_url, timeout=20)
        self.chess_client = http_client

        initial_state = _game_state(self.chess_client, reset=reset_game)
        self.last_state = initial_state
        self.finished = bool(initial_state.get("game_over"))
        prompt_template = (
            CHESS_AGENT_SYSTEM_PROMPT_TEMPLATE
            if include_legal_moves
            else CHESS_AGENT_NO_LEGAL_MOVES_PROMPT_TEMPLATE
        )
        self.system_prompt = prompt_template.render()
        if programmatic_tools:
            self.system_prompt += "\n\n" + PROGRAMMATIC_CHESS_PROMPT
        if self.skills:
            catalog = "\n".join(skill["metadata"] for skill in self.skills.values())
            self.system_prompt += (
                "\n\nReusable skills are available. Call `invoke_skill` with a "
                "skill's name to load its instructions, and follow them in place "
                f"of your default approach.\n\n<skills>\n{catalog}\n</skills>\n"
            )
        opening_instruction = (
            "Choose one move from legal_moves and call play_move."
            if include_legal_moves
            else "Infer a legal move from the board and FEN, then call play_move."
        )
        if programmatic_tools and self.skills:
            opening_instruction = (
                "First call invoke_skill with name 'select-move'. "
                "Follow the loaded skill instructions. "
                "Use run_python to search candidate moves with simulate_move, "
                "then call play_move exactly once inside Python to commit. "
                "Black responds automatically. Do not wait for a human turn. "
                "Continue until game_over is true."
            )
        self.task_prompt = (
            f"Play this game as White. {opening_instruction}\n\n"
            f"{self.format_state(initial_state)}"
        )

    def format_state(self, state: dict[str, Any]) -> str:
        """Format a state according to this run's observation condition."""

        return format_chess_state(state, include_legal_moves=self.include_legal_moves)

    def execute_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Execute model-generated ``play_move`` calls against the chess API."""

        registered = {tool["function"]["name"] for tool in self.tools}
        # play_move and run_python can change the live board. The position the
        # model reasoned about is stale after the first of them, so only the
        # first board-changing call in a response is executed, and any
        # simulate_move calls after it would inspect a stale position.
        board_call_made = False
        messages: list[dict[str, str]] = []

        for call in tool_calls:
            call_id = call.get("id", "") if isinstance(call, dict) else ""
            function = (call.get("function") or {}) if isinstance(call, dict) else {}
            name = function.get("name")
            arguments = function.get("arguments")

            if name not in registered:
                content = _chess_error(
                    f"Unknown tool {name!r}. Available tools: "
                    f"{', '.join(sorted(registered))}."
                )
            elif name in ("play_move", "run_python") and self.finished:
                content = _chess_error(
                    "The game is over, so no further moves can be played."
                )
            elif name in ("play_move", "run_python") and board_call_made:
                content = _chess_error(
                    f"This {name} call was not executed: only one board-changing "
                    "call runs per response, and the position has already "
                    "changed. Read the latest state and choose again."
                )
            elif name == "simulate_move" and board_call_made:
                content = _chess_error(
                    "This simulate_move call was not executed: the board "
                    "already changed earlier in this response, so the "
                    "position it would inspect is stale. Read the latest "
                    "state and simulate again."
                )
            elif name == "play_move":
                board_call_made = True
                content = self._play(arguments)
            elif name == "run_python":
                board_call_made = True
                content = self._run_python(arguments)
            elif name == "simulate_move":
                content = _simulate_move(self.chess_client, arguments)
            elif name == "invoke_skill":
                content = _invoke_skill(self.skills, arguments)
            else:
                content = _chess_error(f"Tool {name!r} is not handled by this agent.")

            messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
        self._track_server_health(messages)
        return messages

    def _track_server_health(self, messages: list[dict[str, str]]) -> None:
        """Update the unreachable-server streak after one step's tool calls.

        Observations are returned to the loop as usual, so the trajectory keeps
        the failing step. The run is stopped before the next model request.
        """

        contents = [str(m.get("content", "")) for m in messages]
        lost = [c for c in contents if SERVER_UNREACHABLE in c or _LIVE_BOARD_LOST in c]
        if not lost:
            if contents:
                self.unreachable_streak = 0
            return
        self.unreachable_streak += 1
        if self.unreachable_streak < self.max_unreachable_steps:
            return
        # Confirm before giving up: one direct read of the live game.
        try:
            _game_state(self.chess_client)
        except Exception as exc:  # noqa: BLE001 - any failure means it is gone
            self.environment_lost = (
                f"The chess server was unreachable for {self.unreachable_streak} "
                f"consecutive steps and a direct state check failed "
                f"({type(exc).__name__}: {exc}). Stopping instead of spending "
                "further model calls."
            )
        else:
            self.unreachable_streak = 0

    def _stop_if_environment_lost(self) -> None:
        if self.environment_lost:
            raise ChessServerUnreachableError(self.environment_lost)

    def maybe_compact_context(self) -> bool:
        # First hook of every loop iteration: stop before a compaction call too.
        self._stop_if_environment_lost()
        return super().maybe_compact_context()

    def query_language_model(self) -> dict[str, Any]:
        self._stop_if_environment_lost()
        return super().query_language_model()

    def _update_state(self, state: dict[str, Any]) -> None:
        self.last_state = state
        self.finished = bool(state.get("game_over"))

    def _play(self, arguments: Any) -> str:
        result = _play_move(self.chess_client, arguments)
        if result.startswith("<chess_error>"):
            return result
        try:
            state = json.loads(result)
        except json.JSONDecodeError:
            return _chess_error("The chess server returned an unreadable state.")
        if not isinstance(state, dict):
            return _chess_error("The chess server returned an unexpected state.")
        self._update_state(state)
        return self.format_state(state)

    def _run_python(self, arguments: Any) -> str:
        output = _run_python(self.env, self.python_sandbox_port, arguments)
        # The snippet may have committed a move, so always re-read the live
        # board; otherwise the model could replay a move that already happened.
        try:
            state = _game_state(self.chess_client)
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            return output + "\n" + _chess_error(
                f"Could not re-read the live board after the snippet ({exc})."
            )
        self._update_state(state)
        return f"{output}\n\nLive board after the snippet:\n{self.format_state(state)}"
