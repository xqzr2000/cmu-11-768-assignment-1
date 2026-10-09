"""The domain-independent ReAct loop shared by both agents.

Part 1 completes the generic loop here; the two subclasses in this package
supply only their own tools and tool executors.
"""

from __future__ import annotations

from copy import deepcopy
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from assignment.env import Environment
from assignment.agent.tools import INVOKE_SKILL_TOOL

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_COMPACTION_KEEP_RECENT_STEPS = 1
DEFAULT_COMPACTION_MAX_TOKENS = 1_200
MAX_OBSERVATION_CHARS = 10_000

# Instructions for the model-generated working memory used by compaction.
COMPACTION_SYSTEM_PROMPT = """You maintain the working memory of an autonomous agent that acts through tools.

You will receive the agent's objective, any earlier working memory, and a transcript
of older steps (assistant actions and the tool observations they produced). Those
steps are about to be deleted from the agent's context, so your summary is the only
record of them the agent will keep. Write concise, factual working memory that lets
the agent continue without redoing work.

Preserve, when present:
- Objective: the task in one or two sentences, and any constraints or rules.
- Environment: working directory, relevant files and paths, symbols, and APIs found.
- Actions: important commands run and what they showed; edits made (file and change).
- Results: concrete outcomes - test names, pass/fail counts, error messages, values.
- Failed approaches: what was tried and why it did not work, so it is not repeated.
- Tests: how to reproduce the problem and how to verify a fix.
- Blockers: open questions or unresolved problems.
- Next action: the single most useful next step.

Rules:
- Be specific: keep exact file paths, function names, commands, and error text.
- Do not copy raw tool output; extract only the facts that matter (a short exact
  error line is fine).
- Do not invent facts or claim progress that the transcript does not show.
- Earlier working memory is superseded by yours, so carry forward anything in it
  that is still relevant.
- Use terse bullet points under the headings above, omitting empty headings.
- Output only the working memory, with no preamble."""

# Sent back to the model when a response contains no tool call, so the loop can
# recover instead of stalling or crashing.
NO_TOOL_CALL_MESSAGE = (
    "Your last response did not contain a tool call, so no action was taken. "
    "Continue working on the task by calling one of the available tools."
)

# Keys of an assistant message that are meaningful to send back to the API.
# Provider-specific extras (refusal, annotations, audio, ...) are dropped so the
# next request stays valid; reasoning fields are kept so the prompt retains the
# model's prior reasoning (set AGENT_STRIP_REASONING=1 if a provider rejects them).
_ASSISTANT_KEYS = ("role", "content", "tool_calls")
_REASONING_KEYS = ("reasoning", "reasoning_content", "reasoning_details")

# Per-observation character budget inside the compaction request.
_COMPACTION_OBSERVATION_CHARS = 3_000


class StepLimitError(Exception):
    """Raised when an agent exhausts its model-call budget."""


def format_tool_output(output: dict[str, Any]) -> str:
    """Format a terminal result as a compact, tagged model observation."""

    elements: list[str] = []
    for key in sorted(output):
        value = output[key]
        if isinstance(value, str) and len(value) > MAX_OBSERVATION_CHARS:
            # Leave room for the elision notice so the formatted value itself,
            # not just its retained source slices, stays below the limit.
            retained_at_each_end = 4_900
            omitted = len(value) - (2 * retained_at_each_end)
            value = (
                f"{value[:retained_at_each_end]}\n"
                f"[{omitted} characters elided; read a narrower range]\n"
                f"{value[-retained_at_each_end:]}"
            )
        elements.append(f"<{key}>{value}</{key}>")
    return "\n".join(elements)


def rough_message_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate prompt tokens without a provider-specific tokenizer."""

    serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    return max(1, math.ceil(len(serialized) / 4))


class Agent:
    """Base class for a ReAct agent with pluggable tools."""

    def __init__(
        self,
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
        self.env = environment
        self.model = model or os.environ.get("OPENAI_MODEL")
        if not self.model:
            raise RuntimeError("OPENAI_MODEL is not set.")

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        base_url = os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        try:
            max_retries = int(os.environ.get("OPENAI_MAX_RETRIES", "5"))
        except ValueError as exc:
            raise RuntimeError("OPENAI_MAX_RETRIES must be an integer.") from exc
        if max_retries < 0:
            raise RuntimeError("OPENAI_MAX_RETRIES must be non-negative.")

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
        )

        self.logs_save_path = logs_save_path
        self.step_limit = step_limit
        self.auto_stop_environment = auto_stop_environment
        if compact_threshold_tokens is not None and compact_threshold_tokens <= 0:
            raise ValueError("compact_threshold_tokens must be positive or None")
        if (
            compaction_keep_recent_steps is not None
            and compaction_keep_recent_steps < 1
        ):
            raise ValueError("compaction_keep_recent_steps must be at least 1")
        if compaction_max_tokens is not None and compaction_max_tokens < 1:
            raise ValueError("compaction_max_tokens must be positive")
        # A None threshold turns compaction off. The other two settings then
        # describe a compaction that never happens, so fall back to the
        # defaults rather than leaving a None for later code to trip over.
        self.compact_threshold_tokens = compact_threshold_tokens
        self.compaction_keep_recent_steps = (
            DEFAULT_COMPACTION_KEEP_RECENT_STEPS
            if compaction_keep_recent_steps is None
            else compaction_keep_recent_steps
        )
        self.compaction_max_tokens = (
            DEFAULT_COMPACTION_MAX_TOKENS
            if compaction_max_tokens is None
            else compaction_max_tokens
        )

        # Each agent supplies its own opening messages: the standing
        # instructions, and the task statement that starts the run.
        self.system_prompt: str = ""
        self.task_prompt: str = ""

        self.api_prompts: list[list[dict[str, Any]]] = []
        self.api_responses: list[dict[str, Any]] = []
        self.compaction_events: list[dict[str, Any]] = []
        self.tools: list[dict[str, Any]] = []
        self.finished = False
        self.steps_taken = 0

        self.skills_path = Path(skills_path) if skills_path is not None else None
        self.skills: dict[str, dict[str, str]] = (
            self.load_skills(self.skills_path) if self.skills_path is not None else {}
        )

        if self.skills:
            self.tools.append(INVOKE_SKILL_TOOL)

        # Interaction history after the opening system/task messages: assistant
        # actions, their linked tool observations, and recovery user messages.
        # Compaction replaces an old prefix of it with ``working_memory``.
        self.history: list[dict[str, Any]] = []
        self.working_memory: str | None = None

    def load_skills(self, skills_path: Path) -> dict[str, dict[str, str]]:
        """Load the skill folders exposed to this agent."""

        skills_path = Path(skills_path)
        if not skills_path.exists():
            raise ValueError(f"Skills path does not exist: {skills_path}")
        if not skills_path.is_dir():
            raise ValueError(f"Skills path is not a directory: {skills_path}")

        skills: dict[str, dict[str, str]] = {}
        for skill_dir in sorted(skills_path.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith((".", "__")):
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                raise ValueError(f"Skill directory {skill_dir} has no SKILL.md")

            content = skill_file.read_text(encoding="utf-8")
            frontmatter = self._parse_skill_frontmatter(content, skill_file)
            name = frontmatter["name"]
            if name in skills:
                raise ValueError(
                    f"Duplicate skill name {name!r} in {skill_file} "
                    f"(already defined by {skills[name]['path']})"
                )
            skills[name] = {
                "name": name,
                "description": frontmatter["description"],
                "metadata": f"name: {name}\ndescription: {frontmatter['description']}",
                "content": content,
                "path": str(skill_file),
            }
        return skills

    @staticmethod
    def _parse_skill_frontmatter(content: str, source: Path) -> dict[str, str]:
        """Parse and validate the YAML frontmatter at the head of a SKILL.md."""

        lines = content.lstrip("\ufeff").splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError(f"{source}: missing YAML frontmatter (expected a leading '---')")
        try:
            end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
        except StopIteration:
            raise ValueError(f"{source}: YAML frontmatter is not closed by '---'") from None

        try:
            data = yaml.safe_load("\n".join(lines[1:end]))
        except yaml.YAMLError as exc:
            raise ValueError(f"{source}: malformed YAML frontmatter: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{source}: frontmatter must be a mapping of keys to values")

        parsed: dict[str, str] = {}
        for key in ("name", "description"):
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{source}: frontmatter needs a non-empty string {key!r}"
                )
            parsed[key] = " ".join(value.split())
        return parsed

    def query_language_model(self) -> dict[str, Any]:
        """Send one tool-enabled Chat Completions request and normalize it."""

        messages = self.build_prompt()
        self.api_prompts.append(deepcopy(messages))
        step_number = self.steps_taken + 1
        print(
            f"[agent] step {step_number}/{self.step_limit}: requesting action",
            flush=True,
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                reasoning_effort="medium",
                max_completion_tokens=4096,
            )
        except Exception as exc:
            print(
                f"[agent] step {step_number}: model request failed after retries "
                f"({type(exc).__name__}: {exc})",
                flush=True,
            )
            raise
        self.api_responses.append(response.model_dump(mode="json"))
        self.steps_taken += 1
        message = self.process_response(response)
        tool_names = [
            call.get("function", {}).get("name", "unknown")
            for call in message.get("tool_calls", [])
            if isinstance(call, dict)
        ]
        if tool_names:
            print(
                f"[agent] step {step_number}: tool call(s): {', '.join(tool_names)}",
                flush=True,
            )
        else:
            print(
                f"[agent] step {step_number}: response contained no parsed tool call; "
                "the loop should preserve the response and continue",
                flush=True,
            )
        return message

    def process_response(self, response: Any) -> dict[str, Any]:
        """Return relevant parts of the language model's response."""

        return response.choices[0].message.model_dump(exclude_none=True)

    def build_prompt(self) -> list[dict[str, Any]]:
        """Assemble the messages for the next request from the agent's state.

        Layout: the standing instructions (system), the task (user), the
        compacted working memory if any (user), then the retained interaction
        history of assistant actions and their linked tool observations. This
        method only reads state, so it is safe to call repeatedly.
        """

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.task_prompt},
        ]
        if self.working_memory:
            messages.append({"role": "user", "content": self._memory_message()})
        messages.extend(deepcopy(self.history))
        return messages

    def _memory_message(self) -> str:
        return (
            "Earlier steps of this session were compacted to save context. "
            "This is your working memory of them; treat it as accurate and "
            "continue from it.\n\n"
            f"<working_memory>\n{self.working_memory}\n</working_memory>"
        )

    @staticmethod
    def _assistant_message(message: dict[str, Any]) -> dict[str, Any]:
        """Keep only the parts of an assistant response that belong in the prompt."""

        keys = _ASSISTANT_KEYS
        if os.environ.get("AGENT_STRIP_REASONING", "").strip() not in ("1", "true"):
            keys = keys + _REASONING_KEYS
        cleaned = {key: deepcopy(message[key]) for key in keys if key in message}
        cleaned["role"] = "assistant"
        tool_calls = [
            call for call in cleaned.get("tool_calls") or [] if isinstance(call, dict)
        ]
        if tool_calls:
            cleaned["tool_calls"] = tool_calls
        else:
            cleaned.pop("tool_calls", None)
        if cleaned.get("content") is None:
            cleaned["content"] = ""
        return cleaned

    def _split_steps(
        self, messages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
        """Group history into steps: an assistant message plus what follows it."""

        leading: list[dict[str, Any]] = []
        steps: list[list[dict[str, Any]]] = []
        for message in messages:
            if message.get("role") == "assistant":
                steps.append([message])
            elif steps:
                steps[-1].append(message)
            else:
                leading.append(message)
        return leading, steps

    def estimate_active_prompt_tokens(self) -> int:
        """Estimate the next prompt, calibrated by the provider's latest usage."""

        current_prompt = self.build_prompt()
        rough_current = rough_message_tokens(current_prompt)
        if not self.api_prompts or not self.api_responses:
            return rough_current

        usage = self.api_responses[-1].get("usage") or {}
        actual_previous = usage.get("prompt_tokens")
        if not isinstance(actual_previous, int):
            return rough_current

        rough_previous = rough_message_tokens(self.api_prompts[-1])
        added_since_previous_request = max(0, rough_current - rough_previous)
        return actual_previous + added_since_previous_request

    @property
    def compaction_enabled(self) -> bool:
        """Whether this agent compacts its context at all."""

        return self.compact_threshold_tokens is not None

    def compact_context(self):
        """Replace parts of prompt with model-generated working memory. Changes the
        content that `build_prompt` emits."""

        keep = max(1, self.compaction_keep_recent_steps)
        leading, steps = self._split_steps(self.history)
        old_steps = steps[:-keep] if len(steps) > keep else []
        recent_steps = steps[-keep:]
        old_messages = leading + [m for step in old_steps for m in step]

        compaction_prompt = [
            {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
            {"role": "user", "content": self._compaction_request(old_messages)},
        ]

        ### Do not modify this section ###
        compaction_response = self.client.chat.completions.create(
            model=self.model,
            messages=compaction_prompt,
            reasoning_effort="medium",
            max_completion_tokens=self.compaction_max_tokens,
        )
        ##################################

        # Use `compaction_response` to update what `build_prompt` emits, but
        # DO NOT modify the object itself. Let the method return it unchanged.
        summary = self._summary_text(compaction_response)
        if not summary:
            # The model returned no usable text (for example, it spent its whole
            # budget reasoning). Fall back to a mechanical record so the old
            # context is still retired rather than silently kept.
            summary = self._fallback_summary(old_messages)
        self.working_memory = summary
        self.history = [m for step in recent_steps for m in step]

        ### Do not modify this section ###
        return compaction_prompt, compaction_response.model_dump(mode="json")
        ##################################

    def _compaction_request(self, old_messages: list[dict[str, Any]]) -> str:
        """Render the objective, prior memory, and old steps for the summarizer."""

        parts = [f"<objective>\n{self.task_prompt}\n</objective>"]
        if self.working_memory:
            parts.append(
                f"<previous_working_memory>\n{self.working_memory}\n"
                "</previous_working_memory>"
            )
        transcript = "\n\n".join(
            self._render_message(message) for message in old_messages
        )
        parts.append(
            "<transcript_to_compact>\n"
            f"{transcript or '(no additional steps)'}\n"
            "</transcript_to_compact>"
        )
        parts.append(
            "Write the updated working memory now. The most recent step(s) stay "
            "in the agent's context verbatim, so focus on what the transcript "
            "above established."
        )
        return "\n\n".join(parts)

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        half = limit // 2
        return f"{text[:half]}\n[... {len(text) - 2 * half} characters omitted ...]\n{text[-half:]}"

    def _render_message(self, message: dict[str, Any]) -> str:
        role = message.get("role", "unknown")
        content = message.get("content")
        if not isinstance(content, str):
            content = "" if content is None else json.dumps(content, ensure_ascii=False)
        if role == "assistant":
            lines = ["[assistant]"]
            if content.strip():
                lines.append(self._clip(content.strip(), 1_500))
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                lines.append(
                    f"tool_call id={call.get('id')} {function.get('name')}: "
                    f"{self._clip(str(function.get('arguments', '')), 2_000)}"
                )
            return "\n".join(lines)
        if role == "tool":
            return (
                f"[tool result for {message.get('tool_call_id')}]\n"
                f"{self._clip(content, _COMPACTION_OBSERVATION_CHARS)}"
            )
        return f"[{role}]\n{self._clip(content, _COMPACTION_OBSERVATION_CHARS)}"

    @staticmethod
    def _summary_text(response: Any) -> str:
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError):
            return ""
        return content.strip() if isinstance(content, str) else ""

    def _fallback_summary(self, old_messages: list[dict[str, Any]]) -> str:
        actions = []
        for message in old_messages:
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                actions.append(
                    f"- {function.get('name')}: "
                    f"{self._clip(str(function.get('arguments', '')), 200)}"
                )
        previous = f"{self.working_memory}\n\n" if self.working_memory else ""
        return (
            f"{previous}Earlier actions (summary unavailable; outputs omitted):\n"
            + ("\n".join(actions) or "- (none)")
        )

    def maybe_compact_context(self) -> bool:
        """Compact before the next action request when the threshold is reached."""

        if not self.compaction_enabled:
            return False

        # Context too short to compact yet
        if self.estimate_active_prompt_tokens() < self.compact_threshold_tokens:
            return False

        prompt_before = deepcopy(self.build_prompt())

        # Not enough steps (each assistant turn corresponds to a step) to force
        # compaction yet
        if (
            len([m for m in prompt_before if m.get("role") == "assistant"])
            <= self.compaction_keep_recent_steps
        ):
            return False

        compaction_prompt, compaction_response = self.compact_context()
        prompt_after = deepcopy(self.build_prompt())
        self.compaction_events.append(
            {
                "step": self.steps_taken,
                "estimated_tokens_before": rough_message_tokens(prompt_before),
                "estimated_tokens_after": rough_message_tokens(prompt_after),
                "active_prompt_before": deepcopy(prompt_before),
                "compaction_prompt": compaction_prompt,
                "compaction_response": compaction_response,
            }
        )
        return True

    def run(self) -> None:
        """Run ReAct steps, always saving the trajectory and stopping the sandbox."""

        try:
            while not self.finished:
                if self.steps_taken >= self.step_limit:
                    raise StepLimitError(
                        f"Agent did not finish within {self.step_limit} steps."
                    )

                # Compact before requesting the next action, never between an
                # action and its observations.
                self.maybe_compact_context()

                # Reason + act: the model returns reasoning/text and tool calls.
                action = self._assistant_message(self.query_language_model())
                tool_calls = action.get("tool_calls", [])
                self.history.append(action)

                if not tool_calls:
                    # Text-only response: keep it, and nudge the model back to
                    # acting rather than ending or crashing the run.
                    self.history.append(
                        {"role": "user", "content": NO_TOOL_CALL_MESSAGE}
                    )
                    continue

                # Observe: one linked tool message per call, in call order.
                observations = self.execute_tool_calls(tool_calls)
                self.history.extend(self._link_observations(tool_calls, observations))
        finally:
            # This block is provided infrastructure. Do not modify it: a
            # trajectory is required even when a run fails.
            if self.logs_save_path:
                path = Path(self.logs_save_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "prompts": self.api_prompts,
                            "responses": self.api_responses,
                            "compactions": self.compaction_events,
                        },
                        indent=2,
                    )
                )
            if self.auto_stop_environment:
                stop = getattr(self.env, "stop", None)
                if callable(stop):
                    stop()

    @staticmethod
    def _link_observations(
        tool_calls: list[dict[str, Any]], observations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Ensure every call in this action has exactly one tool message.

        Providers reject a request in which an assistant tool call has no
        matching tool message. IDs are matched within this action only, since
        some providers reuse IDs such as ``call_0`` across turns.
        """

        remaining = list(observations)
        linked: list[dict[str, Any]] = []
        for call in tool_calls:
            call_id = call.get("id", "")
            match = next(
                (o for o in remaining if o.get("tool_call_id") == call_id), None
            )
            if match is None:
                match = {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": "<error>This tool call produced no result.</error>",
                }
            else:
                remaining.remove(match)
            match = dict(match)
            match.setdefault("role", "tool")
            if not isinstance(match.get("content"), str):
                match["content"] = json.dumps(match.get("content"), ensure_ascii=False)
            linked.append(match)
        return linked

    def execute_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Execute domain-specific calls and return linked tool observations."""

        # You do not need to implement anything here. This method is
        # domain-specific and implemented by the relevant subclasses
        raise NotImplementedError
