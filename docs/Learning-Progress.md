# Assignment 1 — Learning Progress

> A learning-oriented account of where this repo stands against the official
> [CMU 11-768 Assignment 1](https://github.com/cmu-agents/assignment-1/blob/main/ASSIGNMENT.md):
> what it asks for, how we adapted it, what's done, why we left Harness² out, and
> what's left.
>
> **Snapshot:** November 9, 2026 · `uv run pytest` → **138 passed, 3 deselected**; Docker suite 3/3 · **All three parts done for learning** with DeepSeek-V4.1-Flash (+ gpt-5-mini for the A/B) · reports in [`docs/reports/`](reports/) · only optional wrap-up left (§5.5)
>
> Done for learning, not for credit: the point values below are kept only as a measure of where the assignment puts its weight.

---

## TL;DR

| | Status |
| --- | --- |
| **Code (all official TODOs)** | ✅ Implemented and unit-tested on Docker instead of Modal |
| **Run evidence (patches, trajectories, reports)** | ✅ **Part 1** resolved · ✅ **Part 2** both runs resolved + [token report](reports/token-usage-analysis.md) · ✅ **Part 3.2** A/B (4 × 15 steps) + [observation report](reports/observation-experiment.md) · ✅ **Part 3.5** skill + `run_python` search (6 steps) · ⏭️ **Part 3.1** full game skipped by choice (two partial games kept in `artifacts/attempts/`). `artifacts/` is Git-ignored: backed up to `.private/backups/` |
| **Extensions** | ✅ Offline chess evaluator + 3-trial baseline, OpenCode trajectory-logging repair, archived Codex CLI experiment · ✅ CodeAgent vs free OpenCode comparison: CodeAgent 3/3, OpenCode blocked by free quota ([doc](Coding-Agent-Comparison.md)) |
| **Harness²** | ⛔ Looked into, tried setting up, dropped (needs GCP + Tencent WorkBuddy, which goes against our run-everything-ourselves plan) |
| **To finish** | Do the billable runs in order (Part 1 → 2 → 3), write two short reports and `AI_USAGE.md`, then build the ZIP |

The key point: the official grader **replays the files you submit and makes no
new LLM calls**. Code that passes tests earns the unit-test rows. Every row that
needs evidence (the patch replay, compaction evidence, the chess trajectories and
the reports) needs artifacts we still have to produce. **At least 44 of the 100
points** depend on those files.

---

## 1. What the official assignment asks

### 1.1 The big idea: a harness turns a model into an agent

A language model only produces text. An **agent harness** is the software around
it that:

1. builds the prompt (instructions + task + everything that happened so far),
2. reads the model's **tool calls** out of its reply,
3. runs those calls in an environment,
4. sends the results back as **observations**, and
5. repeats until the task is done.

That loop is **ReAct** (Reason + Act). The assignment has you build **one** shared
loop (`Agent` in `base.py`) and then reuse it for two very different agents. That's
how you learn which parts of a harness are general and which belong to one domain.

```text
                SWE-Bench issue
                      |
                      v
buggy chess app -> CodeAgent -> fix.patch -> repaired chess server
                                              ^
                                              |
                                    ChessAgent tools
```

The three parts depend on each other. **Part 3 needs Part 1's patch**: the bug
CodeAgent fixes is a server crash (HTTP 500) when White's move ends the game. Without
that fix, a chess game can't reach the "terminal state" Part 3 is graded on.

### 1.2 Part 1 — Coding agent + chess-app repair (30 pts)

| TODO | What you build | Concept it teaches |
| --- | --- | --- |
| 1.1.a | `Agent.build_prompt` + state tracking | The OpenAI chat format: exactly one `system` message, then `user`, then `assistant`/`tool` turns. Each `tool` message is linked to its call by `tool_call_id` |
| 1.1.b | `CodeAgent` system/task prompts | The system prompt must contain a verbatim `<system_information>` JSON block taken from the environment |
| 1.2 | `Agent.run` — the ReAct loop | Query → parse tool calls → execute → append observations → repeat. Set `finished`; raise `StepLimitError` when the limit is hit |
| 1.3 | `CodeAgent.execute_tool_calls` (`execute`, `send_message`) | **Recoverable errors**: malformed JSON or an unknown tool becomes an observation the model can react to, not a Python exception |
| 1.4 | Skill loading + `invoke_skill` | **Progressive disclosure**: only the skill names and descriptions go in the system prompt. The model calls `invoke_skill` to read the full `SKILL.md`. With no skills loaded, the prompt must not mention `patch.txt` |
| Run | `make run-code-agent` → `make check-part1` | The agent proposing a fix is not the same as verifying it. The checker replays the patch in a fresh testbed |

### 1.3 Part 2 — Context compaction (28 pts)

Every step appends to the prompt, so long tasks get expensive and eventually
overflow the context window. **Compaction** asks the model to summarise an old prefix
of the history into a "working memory" while keeping things safe:

- The original `system` and `task` messages stay **verbatim**.
- The latest complete assistant action stays, **with all its linked tool
  observations**. Splitting a tool call from its result makes the prompt invalid.
- The summary must keep the objective, constraints, files, commands, edits, results,
  failed approaches, tests, blockers and next action.
- No provider-specific compaction endpoint. The model writes the summary itself.

TODO 2.1 = `compact_context`, TODO 2.2 = call `maybe_compact_context()` before every
action. Then run SWE-bench `django__django-15368` (a `bulk_update()` bug with plain
`F()` expressions) at `COMPACT_THRESHOLD=6000`. The run must compact at least once,
materially shrink active context, **and** produce a passing patch. A
`COMPACT_THRESHOLD=0` baseline is the comparison, written up in
`token-usage-analysis.md`.

### 1.4 Part 3 — ChessAgent (40 pts)

Same loop, new tools. The agent plays White and a deterministic bot plays Black.

| Step | Tool | Concept |
| --- | --- | --- |
| 3.1 | `play_move(move)` — strict schema, UCI notation | Tool schema design. Only **one** move from a batch of parallel calls may execute, because each move changes the live board |
| 3.2 | Observation A/B (4 runs) | **The observation is part of the harness.** Showing the board alone vs board + legal moves changes how many illegal moves the model tries |
| 3.3 | `simulate_move(fen, move?)` | A stateless "what if" that leaves the live game alone |
| 3.4 | `run_python(code)` | **Programmatic tool calling**: the model writes Python that calls `simulate_move`/`play_move` as normal functions. It runs in the sandbox (base64-encoded), never in the agent process. Re-read the live board afterwards |
| 3.5 | `invoke_skill` for chess | A skill that gives the model a search strategy. The graded trajectory must show `invoke_skill` → `run_python` searching with `simulate_move` → one `play_move` |

### 1.5 Rules, grading and submission

- **Rules:** don't modify `tests/`, `tasks/` or `chess_app/`; don't change the provided
  logging/cleanup; don't duplicate the ReAct loop in a subclass; don't hard-code
  solutions; never leak credentials.
- **Grading:** 100 points. Private unit tests plus **replay of submitted patches and
  trajectories**. Each row is graded on its own, so a failed run only loses its own row.
- **Submission ZIP:** changed `src/assignment/agent/*.py`, 17 files under `artifacts/`
  (listed in §5), and `AI_USAGE.md`. The instructors also give a quiz on your code,
  so understanding it matters more than having the files.

---

## 2. Our adaptations

I'm a Pitt student working through this on my own (not enrolled at CMU). That leads
to three kinds of change.

### 2.1 Modal → our own Docker sandbox (the main change)

```text
Original:  Agent → Modal environment → remote sandbox (billable)
Ours:      Agent → assignment.env.Environment → agent_sandbox_runtime → Docker → disposable container
```

- `packages/agent-sandbox-runtime/` is a small reusable library that starts, execs
  into, times out and cleans up Docker containers. It is **not** a server or a model.
- `src/assignment/env.py` keeps the **same interface** the agents expect
  (`Environment.execute(...)`), so the agent code didn't change when the backend did.
  **Lesson: make the execution backend replaceable.**
- It runs as Docker-in-Docker inside GitHub Codespaces. No Modal account needed.
- Caveat: Docker isn't a hardened security boundary, and the official private tests
  include "real Modal integration", which we can't satisfy by design.

**Why:** to understand how a sandbox is built, inspect every command that goes in,
control images, timeouts and cleanup, and keep everything under our own control.
OpenCode needs a sandbox anyway.

### 2.2 Models and API

The official default is `deepseek/deepseek-v4-flash-0731` through a course-provided
endpoint, and the A/B uses DeepSeek vs GPT-OSS-120b. We don't get course credits, so
the client stays OpenAI-compatible and configurable. The recorded baseline used
`gpt-5-mini`. The plan for the remaining runs is in §5.2.

### 2.3 Research extensions (beyond the assignment)

| Extension | Where | What it shows |
| --- | --- | --- |
| Offline chess trajectory evaluator, experiment runner, trial aggregator, comparator | `scripts/eval_chess_trajectory.py`, `run_chess_experiment.py`, `aggregate_chess_trials.py`, `compare_chess_evaluations.py` | Deterministic scoring with no LLM judge |
| Baseline 003 | `experiments/eval-harness/baseline-003.json` | 3 × `gpt-5-mini` trials, 3 steps each: 9/9 moves accepted, 0 tool errors, mean 3,628 tokens, **0 games finished** |
| OpenCode harness repair | `tasks/chess-trajectory-logging/`, `src/assignment/opencode_runner.py`, `docs/OPENCODE_BACKEND.md` | A trajectory exposed a logging gap. OpenCode's 2nd attempt, after adding evaluator feedback, passed 2/2 fail-to-pass and 1/1 pass-to-pass |
| CodeAgent vs OpenCode comparison | `docs/Coding-Agent-Comparison.md`, `scripts/compare_coding_agents.py`, `src/assignment/compare.py` | Same task, model family and grader; our ReAct harness on the paid DeepSeek API vs OpenCode on its free DeepSeek model, which can never use an API key (5 layers of enforcement) |
| Codex CLI backend (archived) | `docs/Codex-CLI-Exploration.md`, branch `feature/codex-sandbox` (not merged) | Produced one verified 6-line patch, but needed `danger-full-access` inside Docker. Stopped on risk/complexity grounds |

### 2.4 Rule-compliance notes

- We **added** `tasks/chess-harness-improvement/`, `tasks/chess-trajectory-logging/`
  and extra test files, and **edited** `tests/test_agent.py` (one docstring word) and
  `tests/test_chess_sandbox.py` (Modal → Docker). The official task folders are
  unchanged. Since only `src/assignment/agent/` and `artifacts/` get submitted,
  this is fine for an independent adaptation, but it's worth saying so in `AI_USAGE.md`.
- `cli.py` has an extra `final_observations` field from the OpenCode experiment. It
  works around `Agent.run`'s logging block without touching it, which respects the
  "don't change provided logging" rule.

---

## 3. What we've finished

**Code: every official TODO is implemented** in `base.py`, `code_agent.py`,
`chess_agent.py`, `chess_tools.py` and `tools.py`:

- [x] Prompt construction, ReAct loop, step limit, recoverable tool errors (1.1–1.3)
- [x] Skill discovery with YAML frontmatter validation + `invoke_skill` (1.4)
- [x] Model-generated context compaction, triggered before each action (2.1–2.2)
- [x] `play_move`, `simulate_move`, `run_python`, chess `invoke_skill` (3.1–3.5),
      plus a stale-position guard (reject `simulate_move` after a board-changing call
      in the same response)
- [x] Runners for every graded run (`make run-code-agent`, `run-swebench-agent`,
      `run-chess-agent`, `run-obs-*`, `run-python-skill-agent`), the checkers,
      `report-tokens`, `report-obs` and `package`

**Verification:** 105 offline tests pass today. The Docker suite (3 tests) passed in
the [Nov 2 CI run](https://github.com/xqzr2000/cmu-11-768-assignment-1/actions/runs/41377559231).

**Run evidence:** Part 1 done on Nov 8 with `deepseek-flash` (DeepSeek-V4.1-Flash, DeepSeek API). 13 steps: explore → reproduce the 500 → guard the engine reply on `outcome(claim_draw=True) is None` → edge-case tests → full suite → `invoke_skill` → `patch.txt`. `check-part1`: FAIL_TO_PASS 1/1, PASS_TO_PASS 9/9, **RESOLVED**.

**Part 2 (Nov 9):** both runs fixed the bug the same way: `isinstance(attr, Expression)` → `hasattr(attr, 'resolve_expression')`, so a plain `F()` is no longer wrapped in `Value()`, plus removing the unused import. Both resolved (F2P 1/1, P2P 29/29).

| | Compacted (6,000) | Full context |
| --- | ---: | ---: |
| Steps | 20 | 19 |
| Compactions | 2 (−66%, −61% est.) | 0 |
| Peak prompt | 5,976 | 11,400 |
| Total tokens (incl. 10,205 for summaries) | 105,803 | 140,483 (−24.7% for compaction) |
| Uncached prompt tokens | **17,748** | **6,870** |

Key lesson: compaction cut total tokens but **multiplied uncached tokens by 2.6×**, because rewriting the start of the prompt breaks the provider's prompt cache. On a short run with cheap cache hits it may not be cheaper at all; its real value is on long runs that would outgrow the window. The working-memory summary kept the file and line, both edits, the test results, "lint tools missing" and a next action. Only the baseline re-inserted the bug to prove its new test failed.

**Part 3.1 attempt (Nov 9):** `make run-chess-agent` hit the 200-step limit with no `game-result.json`. What actually happened:

- **Moves 1–56 went fine** (55/56 accepted, one illegal `h1g1`). White promoted and reached **K+Q vs K+B** with `Qa8+`, a winning position.
- **At 1,790 s the sandbox's 30-minute lifetime (`CHESS_TIMEOUT=1800`) expired.** The next **138** `play_move` calls got `Connection refused`, and the model kept retrying, because a transport error comes back as an ordinary recoverable `<chess_error>`.
- **Why it was so slow:** the harness keeps each response's `reasoning_content` in the history (`_REASONING_KEYS`), and chess reasoning is long. Prompts grew 880 → 14.5k (step 10) → 208k (step 30) → 313k (step 58), roughly 10k tokens per move. About 31 s per step meant only 58 steps fit in 30 minutes.
- **Cost:** 56.2M input tokens (99.9% cached) and 304k output, most of it spent after the environment was already gone.

**Part 3.1 attempt 2 (Nov 9):** with stripped reasoning and compaction it was still ~1 min per step, because DeepSeek's *thinking per move* (not the prompt) dominated. Stopped by choice at step 13: the concepts of 3.1 (strict tool schema, recoverable illegal moves, text-only replies, context cost, environment failure) were already observed. Skipping a finished game costs the one `game_over: true` row (4 of 100 points).

**Part 3.2 observation A/B (Nov 9, 15 steps per run):** [full report](reports/observation-experiment.md).

- gpt-5-mini made **3/15 illegal moves with the board only, 0/15 with legal moves listed**: a notation slip (`c2cxd3`), forgetting it had castled (`e1e2`), and a bishop moved sideways (`c4d4`). None was in check.
- DeepSeek made 0 illegal moves in both conditions, but with the list it thought **6× longer** (7,817 vs 1,277 output tokens per step, 43 vs 12 s). That's why the full DeepSeek games were so slow.

**Part 3.5 programmatic tools + skill (Nov 9, 6 steps):**

- **Bug found and fixed (PR #7):** `invoke_skill` was registered twice, giving HTTP 400 "Tool names must be unique".
- **The rerun has the required shape:** `invoke_skill(select-move)` → `run_python` snippets that search with `simulate_move` (2 plies, material evaluation) and commit one `play_move` each. The first move skipped the search, because the skill's Step 1 opening rule says to play `e2e4` directly.
- **Weakness:** with a material-only evaluation most moves tie at −12, and ties go to the alphabetically first UCI string. So the bishop drifted `f1b5` → `b5a4` → `a4b3`. A search is only as good as its evaluation.

**Not finished (optional):** copy the two reports into `artifacts/`, `AI_USAGE.md`, `make package`.

---

## 4. Harness² — what it is, what we tried, why we dropped it

### 4.1 What Harness² is

[Harness²](https://github.com/google-research/harness2) ("recursive agent
harnessing") is an Apache-2.0 research framework from Google Cloud AI Research,
released October 2026, v0.1.0, and not an officially supported Google product. It
**keeps the model frozen and edits the harness**: prompts, tools, memory, skills and
orchestration. It has two loops:

1. **Task level, Propose → Probe → Compose:** run the task once to get a
   *reference trajectory*. An editor model proposes several harness edits, re-runs
   the task under each one, compares the new trajectories with the reference, and
   combines the edits that held up. **No ground-truth answer key is needed.**
2. **Across tasks:** keep the edits and lessons that worked, so the *improvement
   process itself* gets better. That second loop is the "²".

The authors report gains of up to about 11.5 points on Tencent's WorkBuddy-Bench (plus
JobBench and the LAB legal benchmark). These are their own numbers and haven't been
reproduced independently.

### 4.2 What we did

- Read through the Harness² GitHub repo and tried to set it up.
- Stopped once it was clear the real runs needed a **Google Cloud project with
  Vertex AI (billed)** and **Tencent's WorkBuddy** benchmark/evaluation setup.
- While reading, noticed that **Harness²'s idea of a harness is the same thing
  Assignment 1 builds**: system prompt, tool schemas, memory (our compaction), skills
  (our progressive disclosure) and the orchestration loop (our ReAct `run`).
  Assignment 1 builds that by hand. Harness² automates *editing* it.

### 4.3 Why we didn't use it

1. **It goes against the plan of keeping everything under our own control.** The whole
   adaptation exists to remove an external dependency (Modal). Harness² would add two
   more: GCP/Vertex billing and Tencent WorkBuddy.
2. **It doesn't add a new concept for this assignment.** The framework mirrors the
   harness we're already building. The part that's genuinely new, an automated
   optimiser, isn't something Assignment 1 asks for or grades.
3. **We kept the method, not the framework.** Our OpenCode experiment is a manual,
   single-task version of Propose → Probe → Compose:

```text
Harness²                         Our manual loop
--------                         ---------------
reference trajectory      ≈      ChessAgent trajectory (found missing final observations)
Propose (editor model)    ≈      OpenCode writes a patch from a narrow task statement
Probe (re-run, compare)   ≈      fail-to-pass / pass-to-pass tests in a fresh container
Compose                   ≈      we review, add feedback, retry, then accept attempt 2
cross-task memory         ✗      not built (the human carries the lessons)
```

One honest difference: Harness² judges an edit by **re-running the agent** and
comparing behaviour. Our loop judged the patch by **unit tests**. That's why we can say
the logging was fixed but **not** that chess play improved.

---

## 5. What's left to finish

### 5.1 Ordered checklist

Each step depends on the one before it. Run the free checks first, then each billable
run on its own, and inspect its output before moving on.

**0. Free setup**

- [x] Codespace → `make setup && make doctor && make test && make test-docker` (all green)
- [x] Endpoints: `.env` removed; keys come from Codespaces secrets; DeepSeek via the `ds()` helper (§5.2). A probe confirmed DeepSeek accepts `reasoning_effort="medium"` and its own `reasoning_content` passed back

**1. Part 1 — the chess-app fix** (unblocks Part 3)

- [x] `ds make run-code-agent` → `artifacts/fix.patch`, `artifacts/part1-trajectory.json`
- [x] `make check-part1` passes → **8 pts**
- [x] *(extension)* CodeAgent vs OpenCode comparison → [Coding-Agent-Comparison.md](Coding-Agent-Comparison.md): CodeAgent 3/3 resolved (same `outcome()` guard each time, ~111k input / 5.5k output tokens per run); OpenCode's free tier refused every request ("Free usage limit reached"), so it's recorded and closed

**2. Part 2 — compaction on SWE-bench**

- [x] Compacted run, `COMPACT_THRESHOLD=6000` → `django__django-15368.patch` + `-trajectory.json` (20 steps)
- [x] `make check-swebench INSTANCE=django__django-15368` passes → **8 pts**
- [x] Trajectory shows 2 compactions, both cutting the active prompt by >60% → **4 pts**
- [x] Baseline run with `COMPACT_THRESHOLD=0` and distinct filenames (also resolved, 19 steps)
- [x] `make report-tokens`, then the prose rewritten around the cache finding → [`docs/reports/token-usage-analysis.md`](reports/token-usage-analysis.md) (copy to `artifacts/`) → **4 pts**

**3. Part 3 — chess**

- [⏭️] `make run-chess-agent` → `game_over: true` → **4 pts**. Skipped by choice after two partial games (attempt 1: sandbox expired at move 56 in a winning position; attempt 2: ~1 min per step, stopped at step 13). Both are in `artifacts/attempts/`
- [x] Four A/B runs (15 steps each; `deepseek-flash` and gpt-5-mini in the `gpt-oss` slot) → 8 files → **4 pts**
- [x] `make report-obs`, then the prose rewritten from the trajectories → [`docs/reports/observation-experiment.md`](reports/observation-experiment.md) (copy to `artifacts/`) → **4 pts**
- [x] `make run-python-skill-agent STEPS=6` → `invoke_skill` → `run_python` (`simulate_move` search) → one `play_move` per snippet → **6 pts** (after fixing the duplicate tool, PR #7)

**4. Submission**

- [ ] Write `AI_USAGE.md` (Claude, OpenCode, Codex CLI and how each was used; the Docker/model adaptations; the test-file edits from §2.4)
- [ ] `make package`. **Read its output**: it lists missing files but still builds an incomplete ZIP
- [ ] Unzip and inspect: no `.env`, no keys, no extra files → **2 pts**
- [ ] **Download `artifacts/` before deleting the Codespace.** This is the step that went wrong last time

### 5.2 Model plan

| Run | Model | Filenames |
| --- | --- | --- |
| Part 1, Part 2 (both runs), Part 3 basic, Part 3 skill | **`deepseek-flash`** = DeepSeek-V4.1-Flash via `api.deepseek.com` (the official V4-Flash `0731` build isn't offered there) | as specified |
| A/B "model 1" | **`deepseek-flash`** | `part3-*-deepseek*.json` |
| A/B "model 2" | **gpt-5-mini**, in place of GPT-OSS-120b | keep the official `part3-*-gpt-oss*.json` names so the package and report scripts find them, and **state the substitution** in `observation-experiment.md` |

Things to watch:

- **One endpoint per process.** `base.py` reads a single `OPENAI_BASE_URL`/`OPENAI_API_KEY`
  pair, and variables already set beat anything `load_dotenv()` would read. With no `.env`,
  each run names its endpoint explicitly. For DeepSeek, define this once per terminal:
  `ds() { OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY="$DEEPSEEK_API_KEY" OPENAI_MODEL=deepseek-flash "$@"; }`,
  then run `ds make …`. OpenAI runs use the default endpoint and the `OPENAI_API_KEY` secret.
- **A/B model variables.** The Makefile reads `DEEPSEEK_MODEL` / `GPT_OSS_MODEL` from `.env`
  (now gone), so pass them on the command line: `ds make run-obs-deepseek-legal DEEPSEEK_MODEL=deepseek-flash`
  and `OPENAI_MODEL=gpt-5-mini make run-obs-gpt-oss-legal GPT_OSS_MODEL=gpt-5-mini`.
- `scripts/report_observation_experiment.py` labels the second model **"gpt-oss"**.
  Rename the label or add a note so the report doesn't misname gpt-5-mini.

### 5.3 Where OpenCode (free models) fits, and where it doesn't

Our OpenCode sandbox runs free OpenCode models, and `scripts/run_opencode.py` is now
**free-only by default** (default model `opencode/deepseek-v4.1-flash-free`, zero credentials
forwarded, the sandbox checked for keys). Before this change it would have forwarded
`OPENAI_API_KEY` for any model except `mimo-v2.6-flash-free`. Last time `mimo-v2.6-flash-free`
hit "Free usage limit reached".

- ✅ **Good for:** harness-improvement experiments like the trajectory-logging task, the
  [CodeAgent vs OpenCode comparison](Coding-Agent-Comparison.md), or checking a patch idea for
  free before spending on a CodeAgent run.
- ❌ **Can't replace the graded Part 1/Part 2 runs.** The grader replays **CodeAgent's**
  trajectory (`part1-trajectory.json`, the django trajectory with compaction events).
  OpenCode's JSON event log isn't that format, and an OpenCode patch would show
  OpenCode's work, not our harness's.
- **Before any long OpenCode run:** `make opencode-probe` sends one "Reply with exactly READY"
  request. A model showing up in the catalog doesn't mean you can actually run inference on it.

### 5.4 Explicitly out of scope until the ZIP exists

Harness², merging `feature/codex-sandbox`, a `latest_state` chess context policy, an
LLM trajectory judge, and more provider experiments.

---

### 5.5 Remaining (optional wrap-up)

1. Copy the final reports over the generated drafts:
   `cp docs/reports/token-usage-analysis.md docs/reports/observation-experiment.md artifacts/`
2. *(Optional)* Write `AI_USAGE.md` (Claude for code, PRs and reports; OpenCode and Codex experiments; the Docker/model substitutions; the test-file edits from §2.4), then `make package` and inspect the ZIP.
3. Back up `artifacts/` (`tar … .private/backups/`), download the newest `.tgz`, then stop or delete the Codespace.
4. *(Optional follow-ups)* Make `reasoning_effort` configurable and compare move quality and speed. Finish a full game with gpt-5-mini plus the legal-move list, the fastest condition at ~4 s per step.

## 6. Lessons so far

1. **An agent is the model plus the harness.** Prompt layout, tool schemas,
   observations and error handling decide what the model can actually do. The A/B
   experiment measures this directly.
2. **Tool calls and their results have to stay paired.** `tool_call_id` linking is the
   invariant that compaction, parallel-call rejection and trajectory logging all have
   to protect.
3. **Errors should be observations, not crashes.** A recoverable `<chess_error>` lets
   the model fix its own mistake.
4. **Make the backend replaceable.** One adapter (`env.py`) let us swap Modal for Docker
   without touching the agents.
5. **Passing tests ≠ submitted evidence.** We had a fully tested harness and 0/17
   artifacts. Grading replays files, so **back up `artifacts/` before deleting the
   Codespace**.
6. **Verify with an independent check.** A patch counts only after a fresh-container
   replay, and a behaviour claim only after controlled agent runs.
7. **A free tier isn't a guarantee.** OpenCode listed the free DeepSeek model and then refused every request. Probe before planning around free inference, and never let a quota failure fall back to a paid key.
8. **What stays in the context decides speed and cost, not just quality.** Re-sending every move's reasoning turned a chess game into 300k-token prompts and ~31 s moves. Compaction saves tokens but breaks the prompt cache. Measure both before choosing.
9. **Tell "the model made a mistake" apart from "the environment is gone".** A recoverable error is right for an illegal move and wrong for a dead server: 138 retries into a closed port taught nothing and cost the most. A harness needs a circuit breaker for environment failures.
10. **Observation design changes how the model spends its thinking, not just its error rate.** Listing legal moves fixed gpt-5-mini's illegal moves but made DeepSeek deliberate 6× longer. Measure the cost side of a "helpful" observation too.
11. **A search is only as good as its evaluation.** The skill's 2-ply search with a material-only score tied almost every move, and the alphabetical tie-break made the bishop wander.
12. **Use a stop rule.** Codex and Harness² were both interesting. Both were dropped
   once the remaining work was infrastructure rather than learning the assignment's
   concepts.

---

## References

- Official assignment: [cmu-agents/assignment-1 · ASSIGNMENT.md](https://github.com/cmu-agents/assignment-1/blob/main/ASSIGNMENT.md)
- This repo: [`README.md`](../README.md) (§13 Harness², §15–17 status),
  [`docs/OPENCODE_BACKEND.md`](OPENCODE_BACKEND.md),
  [`docs/Codex-CLI-Exploration.md`](Codex-CLI-Exploration.md),
  [`SESSION_NOTES.md`](../tasks/chess-trajectory-logging/experiment-records/SESSION_NOTES.md),
  [`PROGRESS.md`](../experiments/eval-harness/PROGRESS.md)
- Harness² coverage: [Techstrong.ai summary](https://techstrong.ai/?p=72986),
  [Pasquale Pillitteri overview](https://pasqualepillitteri.it/en/news/25395/google-harness2-ai-agents-improve-themselves)
