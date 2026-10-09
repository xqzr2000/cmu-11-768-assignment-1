"""The Part 1 coding agent: fix a software issue and submit a git patch."""

from __future__ import annotations

import json
from typing import Any

from assignment.agent.base import (
    DEFAULT_COMPACTION_KEEP_RECENT_STEPS,
    DEFAULT_COMPACTION_MAX_TOKENS,
    Agent,
    format_tool_output,
)
from assignment.agent.tools import EXECUTE_TOOL, SEND_MESSAGE_TOOL
from assignment.env import Environment

CODE_AGENT_SYSTEM_PROMPT = """You are an autonomous software engineer working in a sandboxed terminal.
You resolve software issues by reading code, reproducing problems, editing source
files, and verifying your changes. Nobody will answer questions or confirm steps,
so work independently until the task is complete.

<system_information>
{system_information}
</system_information>

# How you act
- Every response must call at least one tool. Reason briefly about what you
  learned and what to do next, then act.
- `execute` runs one bash command in a fresh subshell; `cd` and exports do not
  persist, so pass `cwd` instead. Files you write persist.
- Keep output small: search with `grep -rn`, and read files in ranges with
  `sed -n 'START,ENDp'` or `nl -ba FILE | sed -n 'START,ENDp'`.
- Commands cannot prompt for input. Avoid long-running or interactive programs.
- `send_message` ends your session: nothing can be done after it, so call it
  only once the task is completely finished.

# How you work
1. Explore: locate the code relevant to the issue.
2. Reproduce: write a small script or run an existing test that shows the bug.
3. Fix: make a minimal, general change to the source code. Do not modify
   existing tests, and do not special-case the reproduction.
4. Verify: rerun the reproduction and the relevant existing tests, and check
   edge cases.
5. Clean up: remove temporary scripts you created before finishing."""

SKILLS_PROMPT = """# Skills
Skills are reusable instructions for specific kinds of work. The catalog below
lists each skill's name and description. Call `invoke_skill` with a skill's name
to load its full instructions before doing the work it covers, then follow them
in place of your default approach.

<skills>
{catalog}
</skills>"""

CODE_TASK_PROMPT = """Resolve the following issue in the repository at `{cwd}`.

<issue>
{task}
</issue>

Reproduce the problem, fix it in the source code, and verify the fix.{skills_note}"""

class CodeAgent(Agent):
    """An agent that fixes a software issue and submits a git patch."""

    def __init__(
        self,
        task: str,
        environment: Environment,
        model: str | None = None,
        logs_save_path: str | None = None,
        step_limit: int = 100,
        skills_path: str | None = None,
        auto_stop_environment: bool = True,
        compact_threshold_tokens: int | None = None,
        compaction_keep_recent_steps: int = DEFAULT_COMPACTION_KEEP_RECENT_STEPS,
        compaction_max_tokens: int = DEFAULT_COMPACTION_MAX_TOKENS,
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
        self.task = task
        self.submitted_patch = ""

        self.tools.extend([EXECUTE_TOOL, SEND_MESSAGE_TOOL])

        system_information = json.dumps(
            {
                "machine": environment.machine,
                "release": environment.release,
                "system": environment.system,
                "version": environment.version,
            },
            indent=2,
        )
        self.system_prompt = CODE_AGENT_SYSTEM_PROMPT.format(
            system_information=system_information
        )
        skills_note = ""
        if self.skills:
            catalog = "\n\n".join(skill["metadata"] for skill in self.skills.values())
            self.system_prompt += "\n\n" + SKILLS_PROMPT.format(catalog=catalog)
            skills_note = (
                " Check the skills catalog in your instructions and invoke any "
                "skill that applies before doing the work it covers."
            )
        self.task_prompt = CODE_TASK_PROMPT.format(
            cwd=getattr(environment, "cwd", None) or "the current directory",
            task=task.strip(),
            skills_note=skills_note,
        )

    def execute_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Execute ``execute`` and ``send_message`` calls in the code sandbox."""

        messages: list[dict[str, str]] = []
        for call in tool_calls:
            call_id = call.get("id", "") if isinstance(call, dict) else ""
            content = self._execute_one(call)
            messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
        return messages

    def _available_tools(self) -> list[str]:
        return [tool["function"]["name"] for tool in self.tools]

    @staticmethod
    def _error(message: str) -> str:
        return format_tool_output({"error": message})

    @staticmethod
    def _parse_arguments(raw: Any) -> dict[str, Any]:
        """Decode a call's JSON arguments, raising ValueError with a clear reason."""

        if isinstance(raw, dict):
            return raw
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return {}
        if not isinstance(raw, str):
            raise ValueError("tool arguments must be a JSON object string")
        try:
            arguments = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"arguments are not valid JSON ({exc.msg})") from exc
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")
        return arguments

    def _execute_one(self, call: Any) -> str:
        if not isinstance(call, dict):
            return self._error("Malformed tool call.")
        function = call.get("function") or {}
        name = function.get("name")

        if self.finished:
            return self._error(
                "The session already ended with send_message; this call was not run."
            )
        if name not in self._available_tools():
            return self._error(
                f"Unknown tool {name!r}. Available tools: "
                f"{', '.join(self._available_tools())}."
            )
        try:
            arguments = self._parse_arguments(function.get("arguments"))
        except ValueError as exc:
            return self._error(
                f"Could not parse arguments for {name}: {exc}. Nothing was run; "
                "retry with a valid JSON object."
            )

        if name == "execute":
            return self._run_execute(arguments)
        if name == "send_message":
            return self._send_message(arguments)
        if name == "invoke_skill":
            return self._invoke_skill(arguments)
        return self._error(f"Tool {name!r} is not handled by this agent.")

    def _run_execute(self, arguments: dict[str, Any]) -> str:
        allowed = {"command", "shell", "cwd", "timeout", "env"}
        extra = sorted(set(arguments) - allowed)
        if extra:
            return self._error(f"Unexpected argument(s) for execute: {', '.join(extra)}.")

        command = arguments.get("command")
        if isinstance(command, list):
            if not command or not all(isinstance(part, str) for part in command):
                return self._error("`command` as a list must be non-empty strings.")
        elif not isinstance(command, str) or not command.strip():
            return self._error("`command` must be a non-empty string or list of strings.")

        options: dict[str, Any] = {}
        shell = arguments.get("shell")
        if shell is not None:
            if not isinstance(shell, bool):
                return self._error("`shell` must be true, false, or null.")
            options["shell"] = shell
        cwd = arguments.get("cwd")
        if cwd is not None:
            if not isinstance(cwd, str) or not cwd.strip():
                return self._error("`cwd` must be a path string or null.")
            options["cwd"] = cwd
        timeout = arguments.get("timeout")
        if timeout is not None:
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
                return self._error("`timeout` must be a positive number of seconds or null.")
            options["timeout"] = timeout
        env = arguments.get("env")
        if env is not None:
            if not isinstance(env, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in env.items()
            ):
                return self._error("`env` must map variable names to string values.")
            options["env"] = env
        if isinstance(command, list) and "shell" not in options:
            # An argv list is meant to run without a shell.
            options["shell"] = False

        result = self.env.execute(command, **options)
        output = {
            "output": result.get("output", ""),
            "returncode": result.get("returncode"),
        }
        if result.get("exception_info"):
            output["exception_info"] = result["exception_info"]
        return format_tool_output(output)

    def _send_message(self, arguments: dict[str, Any]) -> str:
        summary = arguments.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            return self._error("`summary` must be a non-empty string.")

        self.finished = True
        # Record what was submitted; patch.txt is the submission protocol the
        # skill teaches, so read it if it exists.
        try:
            result = self.env.execute("cat patch.txt")
            if result.get("returncode") == 0:
                self.submitted_patch = result.get("output", "") or ""
        except Exception:  # noqa: BLE001 - the session is ending regardless
            pass
        return format_tool_output({"status": "Message sent. The session has ended."})

    def _invoke_skill(self, arguments: dict[str, Any]) -> str:
        name = arguments.get("name")
        if not isinstance(name, str) or not name.strip():
            return self._error("`name` must be a non-empty string.")
        skill = self.skills.get(name.strip())
        if skill is None:
            return self._error(
                f"Unknown skill {name!r}. Available skills: {', '.join(self.skills)}."
            )
        return skill["content"]
