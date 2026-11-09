# Coding-Agent Comparison: CodeAgent (paid API) vs OpenCode (free)

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
_No comparison trials recorded yet for `chess-terminal-move`. Run the procedure in §4,
then `make compare-report`._
<!-- comparison-results:end -->

## 7. Interpretation guide

Fill this in after the runs, from the records rather than impressions:

- **Outcome:** did both resolve 3/3? If OpenCode had `quota_limited` trials, report them
  separately from real failures, since they reflect the free tier, not the agent.
- **Effort:** steps, tool calls and tokens per resolved trial. A large gap in input
  tokens usually comes from system-prompt and tool-schema size, not the task.
- **Patch content:** do both guard the engine reply on the game outcome, as CodeAgent
  trial 1 did with `outcome(claim_draw=True) is None`? Does either touch more than
  `game.py` or add tests? (OpenCode's test edits are filtered out of its patch.)
- **What it says about our harness:** where did our minimal three-tool ReAct loop
  match a full product, and where did it lose?

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
