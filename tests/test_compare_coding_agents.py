"""Offline tests for the CodeAgent vs OpenCode comparison records and report."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from assignment.compare import (
    RESULTS_END, RESULTS_START, aggregate, codeagent_metrics, evaluation_summary,
    load_records, opencode_metrics, patch_stats, render_report, sanitized_env, trial_dir,
    update_doc,
)
from assignment.eval.harness import TestStatus

PATCH = """diff --git a/src/chess_app/game.py b/src/chess_app/game.py
--- a/src/chess_app/game.py
+++ b/src/chess_app/game.py
@@ -70,3 +70,5 @@
-            reply = self._choose_engine_move()
+            if self._board.outcome(claim_draw=True) is None:
+                reply = self._choose_engine_move()
"""


def test_sanitized_env_strips_every_credential_and_provider_setting():
    env = {
        "PATH": "/usr/bin", "HOME": "/home/vscode", "DOCKER_HOST": "unix:///var/run/docker.sock",
        "OPENAI_API_KEY": "sk-x", "OPENAI_BASE_URL": "https://api.deepseek.com",
        "OPENAI_MODEL": "deepseek-flash", "DEEPSEEK_API_KEY": "ds-x", "ZAI_API_KEY": "z",
        "GITHUB_TOKEN": "ghp", "GITHUB_CODESPACE_TOKEN": "c", "OPENCODE_API_KEY": "o",
        "OPENCODE_MODEL": "opencode/deepseek-v4.1-flash-free",
    }
    clean = sanitized_env(env)
    assert clean == {
        "PATH": "/usr/bin", "HOME": "/home/vscode", "DOCKER_HOST": "unix:///var/run/docker.sock",
        "OPENCODE_MODEL": "opencode/deepseek-v4.1-flash-free",
    }


def test_trial_dir_layout_and_validation(tmp_path):
    assert trial_dir(tmp_path, "chess-terminal-move", "opencode", 2) == (
        tmp_path / "chess-terminal-move" / "opencode" / "trial-2")
    with pytest.raises(ValueError):
        trial_dir(tmp_path, "t", "codex", 1)
    with pytest.raises(ValueError):
        trial_dir(tmp_path, "t", "codeagent", 0)


def test_patch_stats():
    assert patch_stats(PATCH) == {"files": ["src/chess_app/game.py"], "added": 2, "removed": 1}
    assert patch_stats("") is None and patch_stats(None) is None


def test_codeagent_metrics_from_trajectory():
    def response(prompt, completion, tools, cached=0):
        return {
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion,
                      "completion_tokens_details": {"reasoning_tokens": 1},
                      "prompt_tokens_details": {"cached_tokens": cached}},
            "choices": [{"message": {"tool_calls": [{"function": {"name": n}} for n in tools]}}],
        }

    trajectory = {"responses": [response(100, 10, ["execute"]),
                                response(200, 20, ["execute", "invoke_skill"], cached=50),
                                response(300, 5, ["send_message"])],
                  "compactions": []}
    m = codeagent_metrics(trajectory)
    assert m["steps"] == 3 and m["input_tokens"] == 600 and m["output_tokens"] == 35
    assert m["reasoning_tokens"] == 3 and m["cached_input_tokens"] == 50
    assert m["tool_calls"] == {"execute": 2, "invoke_skill": 1, "send_message": 1}
    assert m["compactions"] == 0 and m["token_source"] == "api usage"


def test_opencode_metrics_from_event_log():
    events = "\n".join([
        "not json",
        json.dumps({"type": "step_start", "part": {}}),
        json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "bash"}}),
        json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "edit"}}),
        json.dumps({"type": "step_finish", "part": {"type": "step-finish",
                    "tokens": {"input": 1000, "output": 50, "reasoning": 7, "cache": {"read": 400}}}}),
        json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "bash"}}),
        json.dumps({"type": "step_finish", "part": {"type": "step-finish",
                    "tokens": {"input": 1500, "output": 30, "reasoning": 0, "cache": {"read": 900}}}}),
    ])
    m = opencode_metrics({"events": events})
    assert m["steps"] == 2 and m["input_tokens"] == 2500 and m["output_tokens"] == 80
    assert m["reasoning_tokens"] == 7 and m["cached_input_tokens"] == 1300
    assert m["tool_calls"] == {"bash": 2, "edit": 1}
    assert m["token_source"] == "opencode events"


def test_opencode_metrics_without_usage_marks_tokens_unknown():
    m = opencode_metrics({"events": '{"type":"step_finish"}\n'})
    assert m["steps"] == 1 and m["token_source"] is None


def test_evaluation_summary_from_report():
    report = SimpleNamespace(
        resolved=True, patch_applied=True, error="",
        fail_to_pass={"t1": TestStatus.PASSED},
        pass_to_pass={"t2": TestStatus.PASSED, "t3": TestStatus.FAILED},
    )
    assert evaluation_summary(report) == {
        "resolved": True, "patch_applied": True,
        "fail_to_pass": {"passed": 1, "total": 1},
        "pass_to_pass": {"passed": 1, "total": 2}, "error": None,
    }


def _record(agent, trial, *, resolved, status="ok", wall=60.0, steps=10, tokens=(1000, 100),
            source="api usage", paid=True):
    return {
        "task_id": "chess-terminal-move", "agent": agent, "trial": trial, "status": status,
        "model": "deepseek-flash" if agent == "codeagent" else "opencode/deepseek-v4.1-flash-free",
        "uses_paid_api": paid, "wall_seconds": wall,
        "patch": {"files": ["src/chess_app/game.py"], "added": 4, "removed": 2} if resolved else None,
        "evaluation": ({"resolved": resolved, "fail_to_pass": {"passed": int(resolved), "total": 1},
                        "pass_to_pass": {"passed": 9, "total": 9}} if status == "ok" else None),
        "metrics": {"steps": steps, "input_tokens": tokens[0], "output_tokens": tokens[1],
                    "tool_calls": {"execute": steps}, "token_source": source},
    }


def test_aggregate_and_report():
    records = [
        _record("codeagent", 1, resolved=True, wall=None, steps=13),
        _record("codeagent", 2, resolved=True, wall=90.0, steps=11),
        _record("opencode", 1, resolved=True, wall=120.0, steps=6, source="opencode events", paid=False),
        _record("opencode", 2, resolved=False, status="quota_limited", wall=30.0, steps=0,
                source=None, paid=False),
    ]
    s = aggregate(records)
    assert s["codeagent"]["resolved"] == 2 and s["codeagent"]["mean_wall_seconds"] == 90.0
    assert s["codeagent"]["mean_steps"] == 12 and s["codeagent"]["uses_paid_api"] is True
    assert s["opencode"]["resolved"] == 1 and s["opencode"]["statuses"] == {"ok": 1, "quota_limited": 1}
    assert s["opencode"]["uses_paid_api"] is False
    assert s["opencode"]["mean_input_tokens"] == 1000  # unknown-token trial excluded
    text = render_report(records, "chess-terminal-move")
    assert "| 2/2 |" in text and "| 1/2 |" in text
    assert "quota_limited" in text and "+4/−2" in text
    assert render_report([], "x").startswith("_No comparison trials")


def test_load_records_orders_by_agent_then_trial(tmp_path):
    for agent, trial in (("opencode", 1), ("codeagent", 2), ("codeagent", 1)):
        d = trial_dir(tmp_path, "t", agent, trial)
        d.mkdir(parents=True)
        (d / "run.json").write_text(json.dumps({"agent": agent, "trial": trial}))
    (tmp_path / "t" / "opencode" / "trial-9").mkdir()
    (tmp_path / "t" / "opencode" / "trial-9" / "run.json").write_text("{broken")
    assert [(r["agent"], r["trial"]) for r in load_records(tmp_path, "t")] == [
        ("codeagent", 1), ("codeagent", 2), ("opencode", 1)]


def test_update_doc_replaces_only_marked_section(tmp_path):
    doc = tmp_path / "report.md"
    doc.write_text(f"# Title\n\nintro\n\n{RESULTS_START}\nold\n{RESULTS_END}\n\nfooter\n")
    update_doc(doc, "new table")
    text = doc.read_text()
    assert "old" not in text and "new table" in text
    assert text.startswith("# Title") and text.rstrip().endswith("footer")
    (tmp_path / "plain.md").write_text("no markers")
    with pytest.raises(ValueError):
        update_doc(tmp_path / "plain.md", "x")
