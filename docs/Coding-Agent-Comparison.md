# Coding-Agent Comparison: CodeAgent (paid API) vs OpenCode (free)

> **Result (Nov 9, 2026):** CodeAgent resolved 3/3. OpenCode's free tier refused every request ("Free usage limit reached"), so there were no OpenCode trials. See §6–7.
>
> An extension beyond the official assignment, **not graded**. Same task, same model
> family, same sandbox and the same grader. What changes is the **harness** around the
> model and **who pays for inference**. The graded Part 1 files (`artifacts/fix.patch`,
> `artifacts/part1-trajectory.json`) are only read, never written.

## 1. Question

Given the Part 1 bug (`chess-terminal-move`: the server returns HTTP 500 when White's
move ends the game), how does **our own ReAct harness** compare with a **full
coding-agent product** when both run on a DeepSeek V4.1-Flash model?

- Do both produce a patch that passes the independent replay?
- How much work do they do to get there (steps, tool calls, tokens, wall time)?
- How do their patches differ (size, files, approach)?
- How reliable is each across repeated trials, including free-tier failures?

## 2. The two agents

| | **CodeAgent** | **OpenCode** |
| --- | --- | --- |
| Harness | This repo's `Agent` ReAct loop + `CodeAgent` (`src/assignment/agent/`) | OpenCode CLI v1.19.2, `build` agent, `--auto` |
| Model | `deepseek-flash` = DeepSeek-V4.1-Flash | `opencode/deepseek-v4.1-flash-free` |
| Inference | DeepSeek API (`api.deepseek.com`) — **billable** | OpenCode free tier — **no API key, never a paid API** |
| Tools | `execute`, `send_message`, `invoke_skill` | OpenCode's built-ins (bash, read, edit, grep, …) |
| Task input | `problem_statement.md` + the `submit-task` skill | the same `problem_statement.md`, wrapped in the runner's fix-and-test prompt |
| Submission | agent writes `patch.txt` (skill protocol) | the runner extracts `git diff`, keeping source files only |
| Sandbox | fresh `chess-terminal-move` Docker testbed | the same testbed image, fresh container per trial |
| Step limit / timeout | 200 model steps | 1,200 s process timeout |
| Grader | `scripts/evaluate.py` public tests in a fresh container (same as `make check-part1`) | the same |

**Held constant:** task, testbed image, model family, grader, trial count (3 each).
**Varies:** harness, tool set, prompt wrapper, provider and serving configuration of
the "same" model.

## 3. How "never use the API" is enforced

There are five independent layers, so no single bug can leak a paid key to OpenCode:

1. **Free models only.** `scripts/compare_coding_agents.py run opencode` refuses any
   model that isn't `opencode/<id>-free`, and it never passes `--allow-paid-model`.
2. **The launching process holds no keys.** OpenCode starts in a subprocess whose
   environment has every credential-like variable (`*API_KEY`, `*TOKEN`, `*SECRET`, …)
   and every provider variable (`OPENAI_*`, `DEEPSEEK_*`, `ZAI_*`, …) removed.
3. **The CLI forwards nothing.** `scripts/run_opencode.py` is now free-only by default.
   For a free model it forwards **zero** credentials, even with `--allow-paid-model`.
   Before this change it forwarded `OPENAI_API_KEY` for any model except
   `mimo-v2.6-flash-free`.
4. **The runner refuses.** `OpenCodeRunner(free_only=True)` rejects paid models and any
   `credential_env`, and runs the agent with an empty environment.
5. **The sandbox is checked.** Before OpenCode starts, the runner lists the
   container's environment and aborts if any credential-like name is visible.

Every trial record stores `credential_variables_forwarded` (always `[]`) and
`uses_paid_api: false`.

**Free-tier failures are data.** A "Free usage limit reached" response is recorded as
`quota_limited`, a timeout as `timeout`, and a clean exit with no source change as
`no_patch`. None of them falls back to a paid model.

## 4. Procedure

The comparison uses a Codespace with Docker, `DEEPSEEK_API_KEY` as a Codespaces
secret, and the `ds()` helper:

```bash
ds() { OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY="$DEEPSEEK_API_KEY" OPENAI_MODEL=deepseek-flash "$@"; }
```

```bash
make opencode-probe                      # free: does the free model answer at all?
make compare-import-part1                # CodeAgent trial 1 = the graded Part 1 run (re-graded)
ds make compare-codeagent TRIAL=2        # billable
ds make compare-codeagent TRIAL=3        # billable
make compare-opencode TRIAL=1            # free (probes first, then runs)
make compare-opencode TRIAL=2
make compare-opencode TRIAL=3
make compare-report                      # fills the results section below
```

Each trial writes `artifacts/compare/chess-terminal-move/<agent>/trial-<n>/` with
`fix.patch`, the run log, `console.log`, `evaluation.txt` and `run.json`. These files
are Git-ignored, so back them up (`.private/backups/`) and download them.

## 5. Metrics and their caveats

| Metric | CodeAgent source | OpenCode source | Caveat |
| --- | --- | --- | --- |
| Resolved, FAIL_TO_PASS, PASS_TO_PASS | evaluator | evaluator | identical grader: the most comparable metric |
| Steps | model requests in the trajectory | `step_finish` events | an OpenCode "step" can include several tool calls; not one-to-one |
| Tool calls | `tool_calls` in responses | `tool_use` events | different tool vocabularies |
| Input / output tokens | API `usage` | token fields on OpenCode events (best effort) | `—` means OpenCode didn't report usage; system prompts differ greatly in size |
| Wall time | whole agent process | whole runner process | includes image build and OpenCode's runtime download; trial 1 of CodeAgent (imported) has none |
| Patch files, +/− lines | `fix.patch` | `fix.patch` | size isn't quality; read the patches |

## 6. Results

<!-- comparison-results:start -->
Task: `chess-terminal-move` · public tests replayed in a fresh container for every patch.

| Agent | Model | Paid API | Resolved | Mean wall time (s) | Mean steps | Mean input tok | Mean output tok | Mean patch lines | Outcomes |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| CodeAgent (our ReAct harness, paid API) | deepseek-flash | yes | 3/3 | 57.1 | 12.7 | 111,359 | 5,497 | 8 | ok 3 |

### Per trial

| Agent | Trial | Status | Resolved | F2P | P2P | Wall (s) | Steps | Input tok | Output tok | Tool calls | Patch files | +/− |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| codeagent | 1 | ok | yes | 1/1 | 9/9 | — | 13 | 110,031 | 4,143 | execute×12, invoke_skill×1, send_message×1 | src/chess_app/game.py | +5/−3 |
| codeagent | 2 | ok | yes | 1/1 | 9/9 | 39.3 | 11 | 89,775 | 4,133 | execute×14, invoke_skill×1, send_message×1 | src/chess_app/game.py | +6/−3 |
| codeagent | 3 | ok | yes | 1/1 | 9/9 | 75.0 | 14 | 134,271 | 8,214 | execute×16, invoke_skill×1, send_message×1 | src/chess_app/game.py | +4/−3 |

<!-- comparison-results:end -->


**OpenCode: no usable trials.** All three planned OpenCode trials were blocked before
they started. The free model never produced a token, so there's nothing to grade and no
`run.json` was recorded.

| Check (Nov 9, 2026, ~06:36 UTC, OpenCode 1.19.2) | Result |
| --- | --- |
| Credentials inside the sandbox | none (`env` showed no `*_KEY` / `*_TOKEN`; `GPG_KEY` is the Python image's signing key) |
| `opencode/deepseek-v4.1-flash-free` in the catalog | listed (`opencode models opencode`) |
| First model request | `AI_APICallError: Free usage limit reached …` ~1 s after the request, then retries and a hang until the timeout |
| Earlier attempt (Nov 1, `opencode/mimo-v2.6-flash-free`) | the same error |

The same refusal on two different free models, a week apart, suggests the limit isn't
per model. Whether it's tied to the client, the network (Codespaces) or something else
can't be determined from our side.

## 7. Findings

1. **CodeAgent is reliable on this task: 3/3 resolved, and the same fix every time.**
   Every trial guarded the engine reply with `self._board.outcome(claim_draw=True) is None`.
   That's the same check the app uses for `game_over`, so the two can't disagree. The
   trials differed only in comments and in how many edge cases they checked themselves
   (stalemate, insufficient material, moves after the game ended), which accounts for
   the step range of 11–14.
2. **Our workflow shape held up.** Each trial explored, reproduced the HTTP 500, edited,
   verified, ran the full suite, then `invoke_skill` → `patch.txt` → `send_message`.
   In trials 2–3 the skill was loaded in step 1, alongside the first `execute` call.
3. **Input tokens dominate.** About 111k input vs 5.5k output per run (≈20:1), or roughly
   8.8k input tokens per step. That's because every request re-sends the full history.
   This is the cost that Part 2's context compaction targets.
4. **The harness question is unanswered.** With no OpenCode trial, this experiment can't
   say whether our three-tool loop matches a full coding-agent product.
5. **What we learned instead:**
   - *Being listed isn't being available.* A free model can appear in the catalog and
     still refuse every request. A "free" agent's reliability includes the provider's
     quota, which we don't control.
   - *Policy beat convenience.* The run stopped rather than falling back to a paid model,
     and no credential reached the sandbox. That's the free-only design working.
   - *The tooling improved.* Building the comparison exposed a real credential leak path
     in `run_opencode.py` (fixed in PR #2) and a failure mode where quota errors showed up
     as silent 20-minute timeouts (fixed in PR #3 with `--print-logs`).

**Status: closed as recorded.** The runner is ready. If the free tier becomes usable
again, `make opencode-probe` and then `make compare-opencode TRIAL=1..3` followed by
`make compare-report` will add the OpenCode rows without changing anything else.

## 8. Limitations

- **3 trials per agent** is enough to spot large differences, not to estimate rates.
- **The "same model" may not be served the same way.** The DeepSeek API and OpenCode's
  free tier may differ in serving configuration, reasoning effort, context limits or
  rate limiting. The model id names alone can't settle this.
- **One small task.** A 13-step bug fix may be too easy to separate the harnesses. The
  SWE-bench django task would be a harder follow-up.
- **Trial 1 of CodeAgent is imported.** It's the graded Part 1 run, produced before the
  comparison runner existed, so it has no wall time. Its harness code is the same as
  in trials 2–3 (this change touched only OpenCode and comparison files).
- **OpenCode logs aren't CodeAgent trajectories.** They can't replace any graded
  artifact.
