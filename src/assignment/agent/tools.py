"""Tool definitions exposed to the model, in the OpenAI tool-calling format."""

EXECUTE_TOOL = {
    "type": "function",
    "function": {
        "name": "execute",
        "description": (
            "Run a bash command and return its stdout, stderr, and exit code. "
            "A non-zero exit code is reported, not raised.\n"
            "\n"
            "Every command runs in a new subshell, so a `cd` or an export does not "
            "carry over to the next command. Use the `cwd` and `env` arguments "
            "instead. Files you write do persist.\n"
            "\n"
            "Commands are non-interactive and cannot prompt for input, so pass "
            "flags like `-y` where a command would otherwise ask for confirmation. "
            "Prefer commands that produce little output; when reading a file, use "
            "`head`, `tail`, or `sed -n '10,20p'` rather than printing all of it.\n"
            "\n"
            "Useful patterns:\n"
            "- Create a file: `cat <<'EOF' > newfile.py` ... `EOF`\n"
            "- Edit in place: `sed -i 's/old/new/g' filename.py` (drop the trailing "
            "`g` to replace only the first match; restrict to a line range with "
            "`sed -i '1,10s/old/new/g'`)\n"
            "- View numbered lines: `nl -ba filename.py | sed -n '10,20p'`"
        ),
        # The nested env object intentionally accepts arbitrary variable names,
        # which is incompatible with strict schemas on some providers.
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "anyOf": [
                        {
                            "type": "string",
                            "description": 'A shell command line, e.g. "ls -la | head".',
                        },
                        {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                'The command as an argv list, e.g. ["ls", "-la"]. '
                                "Use this with shell=false when arguments contain "
                                "characters the shell would interpret."
                            ),
                        },
                    ],
                    "description": "The command to run.",
                },
                "shell": {
                    "type": ["boolean", "null"],
                    "description": (
                        "Whether to run the command through a shell, which enables "
                        "pipes, redirection, and globbing. Defaults to true. Set to "
                        "false when passing an argv list."
                    ),
                },
                "cwd": {
                    "type": ["string", "null"],
                    "description": (
                        "Absolute path to run the command in. Defaults to the "
                        "sandbox's current working directory."
                    ),
                },
                "timeout": {
                    "type": ["number", "null"],
                    "description": (
                        "Seconds to allow the command to run before killing it. "
                        "Defaults to no timeout."
                    ),
                },
                "env": {
                    "type": ["object", "null"],
                    "additionalProperties": {"type": "string"},
                    "description": "Extra environment variables to set for this command.",
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}

SEND_MESSAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "send_message",
        "description": ("Send a message to the user."),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": ("Content of the message"),
                },
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
}

INVOKE_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "invoke_skill",
        "description": (
            "Load a skill and return its instructions. A skill is a short guide "
            "for one kind of work, written ahead of time.\n"
            "\n"
            "Call this before starting work a skill covers, and follow what it "
            "says in place of your default approach."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "The skill's directory name, for example `hello-skill`."
                    ),
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
}

PLAY_MOVE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "play_move",
        "description": (
            "Play one move for White on the live game board. The server applies "
            "Black's reply automatically and returns the new position.\n"
            "\n"
            "The move uses UCI notation: the from-square followed by the "
            "to-square, for example `e2e4` or `g1f3`. Castling is the king's "
            "move, for example `e1g1`. A promotion appends the piece letter, for "
            "example `e7e8q`."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "move": {
                    "type": "string",
                    "description": "One legal move for White in UCI notation, e.g. `e2e4` or `e7e8q`.",
                },
            },
            "required": ["move"],
            "additionalProperties": False,
        },
    },
}

SIMULATE_MOVE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "simulate_move",
        "description": (
            "Inspect or simulate a position without changing the live game. "
            "Pass a complete six-field FEN with `move` null to get that "
            "position and its legal moves, or a FEN plus one UCI move (for "
            "either side) to get the position after exactly that one ply. No "
            "opponent reply is made. Returns JSON with `fen`, `squares`, "
            "`turn`, `legal_moves`, `in_check`, `game_over`, `winner`, and "
            "`result`."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "fen": {
                    "type": "string",
                    "description": "A complete six-field FEN string for the position to start from.",
                },
                "move": {
                    "type": ["string", "null"],
                    "description": (
                        "One legal UCI move for the side to move in `fen` (e.g. "
                        "`e2e4`, `e7e8q`), or null to only inspect the position."
                    ),
                },
            },
            "required": ["fen", "move"],
            "additionalProperties": False,
        },
    },
}

RUN_PYTHON_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "Run a Python snippet in the sandbox next to the chess server and "
            "return its stdout, stderr, and error as JSON, followed by the live "
            "board after the snippet.\n"
            "\n"
            "Two functions are already defined; do not import them:\n"
            "- `simulate_move(fen, move=None) -> dict`: stateless; returns the "
            "position (`fen`, `squares`, `turn`, `legal_moves`, `in_check`, "
            "`game_over`, `winner`, `result`) for a FEN, or after one UCI move "
            "from it. Use it to search.\n"
            "- `play_move(move) -> dict`: plays White's move on the live board "
            "(Black replies automatically) and returns the new state. Call it at "
            "most once per snippet, at the end, to commit the chosen move.\n"
            "\n"
            "Both raise RuntimeError when a call is rejected. Use `print` to "
            "report results; the standard library is available."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python source code to execute.",
                },
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
}
