"""Chess tool implementations, decoupled from the agent that registers them.

Every function here takes the HTTP client explicitly instead of reading it off
an agent, so the same code can run in the agent process or inside the sandbox
beside the server it talks to.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

CHESS_PORT = 8000
SANDBOX_PYTHON = "/opt/assignment/sandbox_python.py"
RUN_PYTHON_TIMEOUT = 600


def _chess_error(message: str) -> str:
    """Wrap a problem as an observation the model can recover from."""

    return f"<chess_error>{message}</chess_error>"


def _parse_object(arguments: Any) -> dict[str, Any]:
    """Decode a tool call's raw JSON arguments into an object.

    Raises ``ValueError`` with a message suitable for the model.
    """

    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, bytes):
        arguments = arguments.decode("utf-8", errors="replace")
    if not isinstance(arguments, str):
        raise ValueError(
            f"Arguments must be a JSON object string, got {type(arguments).__name__}."
        )
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Arguments are not valid JSON ({exc.msg}).") from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"Arguments must be a JSON object, got {type(parsed).__name__}."
        )
    return parsed


def _call_api(client: httpx.Client, endpoint: str, payload: dict[str, Any]) -> str:
    """POST to the chess API and serialize the resulting state, or an error."""

    try:
        state = _request_state(client, "POST", endpoint, json=payload)
    except ValueError as exc:
        return _chess_error(f"The server rejected the request: {exc}")
    except httpx.HTTPError as exc:
        return _chess_error(
            f"Could not reach the chess server ({type(exc).__name__}: {exc})."
        )
    except Exception as exc:  # noqa: BLE001 - any failure is recoverable
        return _chess_error(f"Chess request failed ({type(exc).__name__}: {exc}).")
    return json.dumps(state)


def _request_state(
    client: httpx.Client, method: str, endpoint: str, **kwargs: Any
) -> dict[str, Any]:
    """Make one chess API request and validate its JSON response."""

    response = client.request(method, endpoint, **kwargs)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Chess server returned non-JSON ({response.status_code})."
        ) from exc
    if response.status_code >= 400:
        detail = (
            payload.get("detail", payload) if isinstance(payload, dict) else payload
        )
        raise ValueError(str(detail))
    if not isinstance(payload, dict):
        raise RuntimeError("Chess server response must be a JSON object.")
    return payload


def _simulate_move(client: httpx.Client, arguments: str) -> str:
    """New tool: inspect FEN or simulate one ply without changing the game.

    Takes the raw JSON arguments of one tool call and returns the observation
    to send back, so a bad argument or a server error reaches the model as a
    recoverable ``<chess_error>`` instead of ending the run.
    """
    try:
        parsed = _parse_object(arguments)
    except ValueError as exc:
        return _chess_error(str(exc))

    fen = parsed.get("fen")
    if not isinstance(fen, str) or not fen.strip():
        return _chess_error("`fen` is required and must be a non-empty FEN string.")
    move = parsed.get("move")
    if move is not None and not isinstance(move, str):
        return _chess_error("`move` must be a UCI move string or null.")

    payload: dict[str, Any] = {"fen": fen.strip()}
    if move is not None and move.strip():
        payload["move"] = move.strip()
    return _call_api(client, "/api/simulate", payload)


def _play_move(client: httpx.Client, arguments: str) -> str:
    """Existing tool: play one move as White and return the resulting state.

    Takes the raw JSON arguments of one tool call. Returns the new state, or a
    `<chess_error>` observation if the move could not be played.
    """
    try:
        parsed = _parse_object(arguments)
    except ValueError as exc:
        return _chess_error(str(exc))

    move = parsed.get("move")
    if not isinstance(move, str) or not move.strip():
        return _chess_error("`move` is required and must be a UCI move string, e.g. e2e4.")
    return _call_api(client, "/api/move", {"move": move.strip()})


def _run_python(env: Any, port: int, arguments: str) -> str:
    """New tool: run Python with access to the existing registered tools.

    The snippet runs inside the sandbox, which already has the tool
    implementations and the chess server, so code the model wrote never
    executes in the agent process.
    """
    try:
        parsed = _parse_object(arguments)
    except ValueError as exc:
        return _chess_error(str(exc))

    code = parsed.get("code")
    if not isinstance(code, str) or not code.strip():
        return _chess_error("`code` is required and must be a non-empty string.")
    if isinstance(port, bool) or not isinstance(port, int):
        return _chess_error(f"Sandbox port must be an integer, got {port!r}.")

    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    command = f"python {SANDBOX_PYTHON} {port} {encoded}"
    try:
        result = env.execute(command, timeout=RUN_PYTHON_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - report instead of crashing the run
        return _chess_error(
            f"The sandbox could not run the code ({type(exc).__name__}: {exc})."
        )
    if not isinstance(result, dict):
        return _chess_error("The sandbox returned an unexpected result.")

    if result.get("returncode") != 0:
        detail = (
            result.get("exception_info")
            or result.get("stderr")
            or result.get("output")
            or f"exit code {result.get('returncode')}"
        )
        return _chess_error(f"The Python sandbox failed: {str(detail).strip()}")

    stdout = result.get("stdout")
    if stdout is None:
        stdout = result.get("output", "")
    return stdout


def _invoke_skill(skills: dict[str, dict[str, str]], arguments: str) -> str:
    """Existing tool: load one skill's instructions into the conversation."""
    try:
        parsed = _parse_object(arguments)
    except ValueError as exc:
        return _chess_error(str(exc))

    name = parsed.get("name")
    if not isinstance(name, str) or not name.strip():
        return _chess_error("`name` is required and must be a skill name string.")
    skill = skills.get(name.strip())
    if skill is None:
        available = ", ".join(sorted(skills)) or "(none)"
        return _chess_error(f"Unknown skill {name!r}. Available skills: {available}.")
    return skill["content"]


def _game_state(client: httpx.Client, reset: bool = False) -> dict:
    """Read the live game, or start a new one and read the opening position."""

    method, endpoint = ("POST", "/api/reset") if reset else ("GET", "/api/state")
    return _request_state(client, method, endpoint)
