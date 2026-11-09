"""Compare two coding agents on the same task: CodeAgent (paid API) vs OpenCode (free).

Everything here is offline and deterministic: it reads saved patches, CodeAgent
trajectories, OpenCode run logs and evaluator reports, and turns them into
per-trial records and a Markdown report. Running the agents and the evaluator
lives in ``scripts/compare_coding_agents.py``.

Layout of one trial::

    artifacts/compare/<task-id>/<agent>/trial-<n>/
        fix.patch          candidate patch (absent when the agent produced none)
        trajectory.json    CodeAgent run log, or
        opencode-run.json  OpenCode run log (JSON events + status)
        console.log        everything the agent process printed
        evaluation.txt     evaluator summary (fresh container, public tests)
        run.json           the record this module builds
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping

from assignment.opencode_runner import credential_like_names

AGENTS = ("codeagent", "opencode")
AGENT_LABELS = {
    "codeagent": "CodeAgent (our ReAct harness, paid API)",
    "opencode": "OpenCode (free model, no API key)",
}
DEFAULT_ROOT = Path("artifacts/compare")
# Provider variables the OpenCode side must never inherit, credential or not:
# an endpoint or model name for a paid API has no business there either.
_PROVIDER_PREFIXES = ("OPENAI_", "DEEPSEEK_", "ANTHROPIC_", "ZAI_", "GEMINI_",
                      "GOOGLE_GENERATIVE_AI_", "OPENROUTER_", "OPENCODE_API")
RESULTS_START = "<!-- comparison-results:start -->"
RESULTS_END = "<!-- comparison-results:end -->"


def trial_dir(root: Path, task_id: str, agent: str, trial: int) -> Path:
    if agent not in AGENTS:
        raise ValueError(f"agent must be one of {AGENTS}, not {agent!r}")
    if trial < 1:
        raise ValueError("trial numbers start at 1")
    return Path(root) / task_id / agent / f"trial-{trial}"


def sanitized_env(environ: Mapping[str, str]) -> dict[str, str]:
    """Copy of the environment with every credential and provider setting removed.

    This is what the OpenCode subprocess runs with, so the process that starts
    the sandbox never even holds a paid API key.
    """
    drop = set(credential_like_names(environ)) | {
        name for name in environ if name.upper().startswith(_PROVIDER_PREFIXES)
    }
    return {k: v for k, v in environ.items() if k not in drop}


def patch_stats(patch: str | None) -> dict[str, Any] | None:
    if not patch or not patch.strip():
        return None
    files, added, removed = [], 0, 0
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            if match:
                files.append(match.group(2))
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return {"files": files, "added": added, "removed": removed}


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def codeagent_metrics(trajectory: Mapping[str, Any]) -> dict[str, Any]:
    """Steps, token usage and tool calls from a saved CodeAgent trajectory."""
    responses = trajectory.get("responses") or []
    prompt = completion = reasoning = cached = 0
    tools: dict[str, int] = {}
    for response in responses:
        usage = (response or {}).get("usage") or {}
        prompt += _int(usage.get("prompt_tokens"))
        completion += _int(usage.get("completion_tokens"))
        reasoning += _int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))
        cached += _int((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or _int(
            usage.get("prompt_cache_hit_tokens"))
        for choice in (response or {}).get("choices") or []:
            for call in ((choice or {}).get("message") or {}).get("tool_calls") or []:
                name = ((call or {}).get("function") or {}).get("name") or "unknown"
                tools[name] = tools.get(name, 0) + 1
    return {
        "steps": len(responses),
        "input_tokens": prompt,
        "output_tokens": completion,
        "reasoning_tokens": reasoning,
        "cached_input_tokens": cached,
        "tool_calls": dict(sorted(tools.items())),
        "compactions": len(trajectory.get("compactions") or []),
        "token_source": "api usage" if responses else None,
    }


def _events(raw: Any) -> Iterable[dict]:
    """OpenCode ``--format json`` output: one JSON object per line, mixed with noise."""
    if isinstance(raw, list):
        yield from (e for e in raw if isinstance(e, dict))
        return
    for line in str(raw or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def opencode_metrics(record: Mapping[str, Any]) -> dict[str, Any]:
    """Best-effort steps, tokens and tool calls from an OpenCode JSON event log.

    OpenCode reports usage on its step-finish events; if a version omits it,
    the token fields stay at 0 and ``token_source`` is None.
    """
    steps = input_tokens = output_tokens = reasoning = cached = 0
    found_tokens = False
    tools: dict[str, int] = {}
    for event in _events(record.get("events")):
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        kind = str(event.get("type") or "").replace("-", "_")
        part_kind = str(part.get("type") or "").replace("-", "_")
        if kind == "step_finish" or part_kind == "step_finish":
            steps += 1
            tokens = part.get("tokens") or event.get("tokens")
            if isinstance(tokens, dict):
                found_tokens = True
                input_tokens += _int(tokens.get("input"))
                output_tokens += _int(tokens.get("output"))
                reasoning += _int(tokens.get("reasoning"))
                cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
                cached += _int(cache.get("read"))
        elif kind == "tool_use" or part_kind == "tool":
            name = part.get("tool") or event.get("tool") or "unknown"
            tools[str(name)] = tools.get(str(name), 0) + 1
    return {
        "steps": steps,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning,
        "cached_input_tokens": cached,
        "tool_calls": dict(sorted(tools.items())),
        "compactions": None,
        "token_source": "opencode events" if found_tokens else None,
    }


def evaluation_summary(report: Any) -> dict[str, Any]:
    """Plain-data view of an ``assignment.eval`` Report."""
    def count(group: Mapping[str, Any]) -> tuple[int, int]:
        passed = sum(1 for s in group.values() if getattr(s, "value", s) == "PASSED")
        return passed, len(group)

    f2p = count(report.fail_to_pass)
    p2p = count(report.pass_to_pass)
    return {
        "resolved": bool(report.resolved),
        "patch_applied": bool(report.patch_applied),
        "fail_to_pass": {"passed": f2p[0], "total": f2p[1]},
        "pass_to_pass": {"passed": p2p[0], "total": p2p[1]},
        "error": report.error or None,
    }


def load_records(root: Path, task_id: str) -> list[dict[str, Any]]:
    records = []
    for path in sorted((Path(root) / task_id).glob("*/trial-*/run.json")):
        try:
            records.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(records, key=lambda r: (AGENTS.index(r.get("agent", "codeagent"))
                                          if r.get("agent") in AGENTS else 99, r.get("trial", 0)))


def _fmt(value: Any, digits: int = 0) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _mean(values: list) -> float | None:
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return mean(values) if values else None


def aggregate(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for agent in AGENTS:
        rows = [r for r in records if r.get("agent") == agent]
        if not rows:
            continue
        resolved = sum(1 for r in rows if (r.get("evaluation") or {}).get("resolved"))
        metrics = [r.get("metrics") or {} for r in rows]
        statuses: dict[str, int] = {}
        for r in rows:
            statuses[r.get("status", "unknown")] = statuses.get(r.get("status", "unknown"), 0) + 1
        summary[agent] = {
            "trials": len(rows),
            "resolved": resolved,
            "statuses": statuses,
            "models": sorted({r.get("model") or "?" for r in rows}),
            "mean_wall_seconds": _mean([r.get("wall_seconds") for r in rows]),
            "mean_steps": _mean([m.get("steps") for m in metrics]),
            "mean_input_tokens": _mean([m.get("input_tokens") for m in metrics if m.get("token_source")]),
            "mean_output_tokens": _mean([m.get("output_tokens") for m in metrics if m.get("token_source")]),
            "mean_patch_lines": _mean([
                (r["patch"]["added"] + r["patch"]["removed"]) for r in rows if r.get("patch")
            ]),
            "uses_paid_api": any(r.get("uses_paid_api") for r in rows),
        }
    return summary


def render_report(records: list[dict[str, Any]], task_id: str) -> str:
    if not records:
        return f"_No comparison trials recorded yet for `{task_id}`._\n"
    summary = aggregate(records)
    lines = [
        f"Task: `{task_id}` · public tests replayed in a fresh container for every patch.",
        "",
        "| Agent | Model | Paid API | Resolved | Mean wall time (s) | Mean steps | Mean input tok | Mean output tok | Mean patch lines | Outcomes |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for agent, s in summary.items():
        outcomes = ", ".join(f"{k} {v}" for k, v in sorted(s["statuses"].items()))
        lines.append(
            f"| {AGENT_LABELS[agent]} | {', '.join(s['models'])} | {'yes' if s['uses_paid_api'] else 'no'} "
            f"| {s['resolved']}/{s['trials']} | {_fmt(s['mean_wall_seconds'], 1)} | {_fmt(s['mean_steps'], 1)} "
            f"| {_fmt(s['mean_input_tokens'])} | {_fmt(s['mean_output_tokens'])} "
            f"| {_fmt(s['mean_patch_lines'], 1)} | {outcomes} |"
        )
    lines += [
        "",
        "### Per trial",
        "",
        "| Agent | Trial | Status | Resolved | F2P | P2P | Wall (s) | Steps | Input tok | Output tok | Tool calls | Patch files | +/− |",
        "| --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for r in records:
        ev = r.get("evaluation") or {}
        m = r.get("metrics") or {}
        patch = r.get("patch")
        has_tokens = bool(m.get("token_source"))
        cells = [
            str(r.get("agent")),
            str(r.get("trial")),
            str(r.get("status")),
            ("yes" if ev.get("resolved") else "no") if ev else "—",
            _ratio(ev.get("fail_to_pass")),
            _ratio(ev.get("pass_to_pass")),
            _fmt(r.get("wall_seconds"), 1),
            _fmt(m.get("steps")),
            _fmt(m.get("input_tokens")) if has_tokens else "—",
            _fmt(m.get("output_tokens")) if has_tokens else "—",
            ", ".join(f"{k}×{v}" for k, v in (m.get("tool_calls") or {}).items()) or "—",
            ", ".join(patch["files"]) if patch else "—",
            f"+{patch['added']}/−{patch['removed']}" if patch else "—",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _ratio(group: Mapping[str, int] | None) -> str:
    return f"{group['passed']}/{group['total']}" if group else "—"


def update_doc(path: Path, results_markdown: str) -> None:
    """Replace the text between the results markers in a Markdown document."""
    text = Path(path).read_text()
    if RESULTS_START not in text or RESULTS_END not in text:
        raise ValueError(f"{path} has no {RESULTS_START} … {RESULTS_END} markers")
    head, rest = text.split(RESULTS_START, 1)
    _, tail = rest.split(RESULTS_END, 1)
    Path(path).write_text(f"{head}{RESULTS_START}\n{results_markdown}\n{RESULTS_END}{tail}")
