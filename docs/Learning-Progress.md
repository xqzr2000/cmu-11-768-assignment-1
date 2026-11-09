# Assignment 1 — Learning Progress

> A learning-oriented account of where this repo stands against the official
> [CMU 11-768 Assignment 1](https://github.com/cmu-agents/assignment-1/blob/main/ASSIGNMENT.md):
> what it asks for, how we adapted it, what's done, why we left Harness² out, and
> what's left.
>
> **Snapshot:** November 8, 2026 · `uv run pytest` → **128 passed, 3 deselected**; Docker suite 3/3 · **Part 1 resolved** with DeepSeek-V4.1-Flash

---

## TL;DR

| | Status |
| --- | --- |
| **Code (all official TODOs)** | ✅ Implemented and unit-tested on Docker instead of Modal |
| **Run evidence (patches, trajectories, reports)** | 🟡 **Part 1 done** (`fix.patch` + `part1-trajectory.json`, `check-part1` RESOLVED). Parts 2–3 not run yet. `artifacts/` is Git-ignored, so back it up |
| **Extensions** | ✅ Offline chess evaluator + 3-trial baseline, OpenCode trajectory-logging repair, archived Codex CLI experiment · 🧪 CodeAgent vs free OpenCode comparison ([doc](Coding-Agent-Comparison.md)) |
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

**Not finished:** the other 15 required artifacts, `AI_USAGE.md`.

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
- [ ] *(extension)* CodeAgent vs OpenCode comparison, 3 trials each → [Coding-Agent-Comparison.md](Coding-Agent-Comparison.md)

**2. Part 2 — compaction on SWE-bench**

- [ ] Compacted run, `COMPACT_THRESHOLD=6000` → `django__django-15368.patch` + `-trajectory.json`
- [ ] `make check-swebench INSTANCE=django__django-15368` passes → **8 pts**
- [ ] Check the trajectory shows ≥1 compaction event and a smaller active context → **4 pts**
- [ ] Baseline run with `COMPACT_THRESHOLD=0` and **distinct** filenames (`-baseline.patch`, `-baseline-trajectory.json`)
- [ ] `make report-tokens` → write `artifacts/token-usage-analysis.md` (trends + tradeoffs) → **4 pts**

**3. Part 3 — chess**

- [ ] `make run-chess-agent` → `part3-trajectory.json` + `game-result.json` with `game_over: true` → **4 pts**
- [ ] Four A/B runs → 8 files → **4 pts**
- [ ] `make report-obs` → `artifacts/observation-experiment.md` (play_move calls, illegal rejections, invalid-move rate, game_over per run) → **4 pts**
- [ ] `make run-python-skill-agent` → `part3-python-skill-trajectory.json` showing `invoke_skill` → `run_python`(`simulate_move` search) → one `play_move` → **6 pts**

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
7. **Use a stop rule.** Codex and Harness² were both interesting. Both were dropped
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
