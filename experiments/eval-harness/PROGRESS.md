# CMU 11-768 — Evaluation Harness and Coding-Agent Experiments

**Progress record and next-session handoff**  
**Updated:** 2026-11-02 UTC (2026-11-01 Pacific)  
**Repository:** `https://github.com/xqzr2000/cmu-11-768-assignment-1`  
**Current local branch:** `experiment/chess-context-window`  
**Current branch base / last verified commit:** `9bed843` — `Record first three-trial chess evaluation baseline`  
**Baseline and progress documentation:** merged into `experiment/eval-harness` at `9bed843`  
**Current working-tree status:** `tasks/chess-context-window/` is **untracked**; no chess-agent source changes have been made on this branch.  
**Next milestone:** **Step 54 — Integrate Codex CLI as a third coding-agent option in a disposable Docker sandbox.**

> **Resume here:** Our evaluation harness is operational, and the first real three-trial chess baseline is recorded. We explored OpenCode with its listed free models, verified a safe, clean sandbox, and diagnosed a provider-side **“Free usage limit reached”** error for the attempted MiMo model. **No OpenCode patch was produced.** Keep CodeAgent and OpenCode intact; add Codex CLI as a third coding agent, using the existing OpenAI API key initially and testing authentication/cost controls before a full coding task.

## 1. Research goal and architecture

This repository adapts CMU 11-768 Assignment 1 into a reproducible workflow for improving an AI agent's *harness* from measured trajectories:

1. Run a **ChessAgent** in a Docker-backed chess environment inside GitHub Codespaces, without requiring Modal.
2. Record full trajectories: prompts, model responses, chess actions, tool observations, outcomes, and token usage.
3. Evaluate these trajectories **offline and deterministically**, without an LLM judge.
4. Repeat trials, aggregate results, and compare controlled harness variants.
5. Use a coding agent to propose a narrowly scoped change, inspect the resulting patch, run regression tests, and repeat the evaluation.

**Keep two roles separate:**

- **Chess-playing agent:** `ChessAgent` using `gpt-5-mini` through the OpenAI API for the measured game trials.
- **Harness-development agent:** CodeAgent, OpenCode, or the planned Codex CLI. This agent edits Python code; it is **not** the chess-playing model under evaluation.

### Coding-agent options

| Coding agent | State | Isolation and purpose |
|---|---|---|
| Repository's original **CodeAgent** | Already part of the project | Existing assignment coding agent; preserve it |
| **OpenCode** | Integrated and sandbox-tested; selected free-model inference blocked | Disposable Docker testbed, clean Git snapshot, file allowlist on generated patches |
| **Codex CLI** | **Planned; not yet installed or integrated** | Third coding agent in a separate Docker sandbox, initially using the existing OpenAI API key |

The goal is to preserve all three options. Over time, comparable tasks and output records should make their engineering behavior observable (patches, tool operations, failures, token/cost measurements), while the chess evaluator independently measures the resulting harness.

## 2. Completed evaluation infrastructure

| Component | Location / implementation | Verified evidence |
|---|---|---|
| Sandbox runtime and chess API | `packages/agent-sandbox-runtime/`, `ChessSandbox`, `assignment.env.Environment` | Docker integration suite: **3 passed** |
| Chess-playing agent | `src/assignment/agent/chess_agent.py`, shared `agent/base.py` | Existing chess-agent and tool-ordering tests |
| Offline trajectory evaluator | `scripts/eval_chess_trajectory.py` | Regression-tested |
| Single-report comparator | `scripts/compare_chess_evaluations.py` | Regression-tested; not yet an aggregate-summary comparator |
| Experiment planner and executor | `scripts/run_chess_experiment.py` | Real single trial and real three-trial batch completed |
| Trial aggregator | `scripts/aggregate_chess_trials.py` | 10 dedicated aggregation tests |
| Resilient batch orchestration | `execute_experiment()` | 13 mocked batch tests; trial 3 still attempted if trial 2 fails |
| Multi-trial CLI | `--trials N --execute` | 10 CLI tests including batch success/failure and output overwrite checks |

**Latest verified full suite:** `uv run pytest` → **105 passed, 3 deselected**; `uv run pytest -m docker -v` → **3 passed**. These were checked after restarting Codespaces, before the new experiment branch was created. The branch currently contains no committed source-code changes beyond that verified baseline.

### Relevant Git history

```text
9bed843 Record first three-trial chess evaluation baseline
cf7ae35 Add files via upload (experiments/eval-harness/PROGRESS.md)
24a03bc Enable multi-trial chess experiments from CLI
19a5a64 Add resilient multi-trial chess experiment orchestration
9be374d Add offline chess trial aggregation and regression tests
983691c Record first automated chess evaluation baseline
```

The local baseline commit was first made as `4a42d5a`, but a push was rejected because `PROGRESS.md` had been uploaded to GitHub independently. A **non-force rebase** and push resolved the divergence; the resulting baseline commit is **`9bed843`**. `experiment/chess-context-window` was branched from that commit.

## 3. Verified chess baselines

| Experiment | Configuration | Outcomes | Recorded action tokens |
|---|---|---|---|
| `baseline-001` | Earlier manual, 1 trial | 3 accepted moves, step limit | 4,272 |
| `baseline-unpatched-002` | Automated, 1 trial | 3 accepted moves, step limit | 3,754 |
| `baseline-unpatched-003` | Automated, **3 trials**, `gpt-5-mini`, 3 steps/trial, unpatched chess application | 9/9 accepted moves; 0 tool errors; 3/3 reports; all reached step limit | 3,696 / 3,626 / 3,562; **mean 3,628** |

**Baseline 003 record:** `experiments/eval-harness/baseline-003.json` (committed at `9bed843`).  
**Raw per-trial artifacts:** `artifacts/eval-harness/baseline-unpatched-003/` (local, Git-ignored); includes `plan.json`, `summary.json`, and three sets of trajectory/result/report/status JSON files.

All three Baseline 003 trials selected the same White moves:

```text
e2e4  →  g1f3  →  e4d5
```

All reached the same final FEN:

```text
rnb1kbnr/ppp2ppp/8/3qp3/8/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 4
```

All trials ended with `step_limit`, **not game completion**. Move acceptance and short-horizon reliability do not measure chess-playing strength. The previous 3,754-token single trial versus 3,628-token three-trial mean also does **not** show a harness improvement: no intentional harness change occurred, and the sample is small.

## 4. What trajectory analysis revealed

After Baseline 003, we inspected each trial's actual recorded prompts and token usage. The three trials had exactly the same **input** token counts at each step:

| Step | Input tokens | Messages in prompt | Serialized prompt characters | Tool-observation content characters |
|---|---:|---:|---:|---:|
| 1 | 707 | 2 | 1,393 | 0 |
| 2 | 1,097 | 4 | 2,293 | 615 |
| 3 | 1,494 | 6 | 3,201 | 1,238 |

Per trial, input tokens totaled **3,298**. Output tokens were **398**, **328**, and **264**, giving an average of **330 output tokens** and **3,628 total recorded action tokens**. Approximately **91%** of recorded tokens were input tokens. **No compactions** occurred.

More detailed Step 3 prompt composition (serialized characters): system **693**, user **700**, previous assistant messages **368**, tool messages **1,440**. Old board observations are therefore a plausible source of redundant context, but we have **not yet proved** they can be removed without changing behavior.

### Source-code findings

- `Agent.build_prompt()` in `src/assignment/agent/base.py` creates `[system, initial user/task, optional working memory, ...deepcopy(history)]`.
- `Agent.run()` appends assistant actions and linked tool observations to `self.history` after each model step. Its trajectory-writing and sandbox-cleanup `finally` block must remain untouched.
- `ChessAgent` currently **does not override** `build_prompt()`.
- `ChessAgent._play()` updates `last_state` and returns a **complete formatted chess state** after each successful `play_move`.
- Chess observations include FEN, board, legal moves, recent move history, status, and other metadata.
- Assistant tool calls and tool replies must remain correctly matched by `tool_call_id`.

**Working hypothesis:** An **opt-in chess-specific `latest_state` prompt policy** could reduce repeated past board states while preserving the current position, legal moves, tool-call pairing, full execution logs, and the original behavior as default (`full`). It must fall back safely for errors or unusual tool sequences. Do **not** modify the shared `Agent.run()` loop to implement this experiment.

## 5. Experiment branch and task specification

**Current branch:** `experiment/chess-context-window`, created from `9bed843`.

Created locally (currently untracked):

```text
tasks/chess-context-window/problem_statement.md
tasks/chess-context-window/Dockerfile
tasks/chess-context-window/experiment-records/SESSION_NOTES.md
```

The problem statement defines the `full` and `latest_state` policies, the single permitted source file (`src/assignment/agent/chess_agent.py`), fallback conditions, safety requirements, and offline test expectations. The Dockerfile was copied from the prior chess-harness OpenCode experiment. `SESSION_NOTES.md` records the failed OpenCode attempt and provider error.

**These files have not yet been committed or pushed.** Do not assume the experimental task survives deletion of this Codespace until it is committed or backed up.

Also note: `scripts/run_chess_experiment.py --patch` currently refers to a **chess application patch inside the sandbox**, *not* to a change in the Python ChessAgent harness. To compare `full` against `latest_state`, later record the policy explicitly in each experiment plan and evaluate the source modification from a controlled Git commit; do not conflate these two patch mechanisms.

## 6. OpenCode exploration — completed tests, failure, and lessons

### 6.1 Clean sandbox and existing integration

We reused the repository's `OpenCodeRunner` and Docker sandbox infrastructure. The testbed was built from `git archive HEAD` at `9bed843`, not the entire working directory. The verified export contained **102 files** and excluded `.git`, `.venv`, and private `artifacts/`.

Inside a disposable Docker container:

- Git initialized with a clean baseline commit; working tree clean.
- `OPENAI_API_KEY` was **absent** from the container.
- Private experiment artifacts were **absent**.
- Existing chess-agent tests passed: **9 passed in 0.86s**.
- Sandbox cleanup succeeded.

The container Dockerfile uses `python:3.12-slim`, installs `git`, copies the clean snapshot to `/testbed`, initializes a testbed Git repository, and installs Python project dependencies and `pytest`.

**Security lesson:** The `OpenCodeRunner` file allowlist validates generated changes; it is not a complete runtime filesystem or network permission boundary. A clean, disposable container and careful secret handling are still essential.

### 6.2 OpenCode version and model catalog

OpenCode **1.19.2** installed successfully in the disposable container. Running its model-listing command returned these free-labeled models at the time of the experiment:

```text
opencode/cat-jam-free
opencode/deepseek-v4.1-flash-free
opencode/longcat-2.5-preview-free
opencode/mimo-v2.6-flash-free
opencode/muse-spark-1.3-contributor-free
opencode/nemotron-3-ultra-free
opencode/nemotron-3.5-lightning-free
opencode/nemotron-3.5-super-vl-free
opencode/space-bunny-free
```

**Catalog visibility does not guarantee that inference is permitted or free usage remains available.** Only `opencode/mimo-v2.6-flash-free` was actually attempted for this task and probed diagnostically; the other listed models were **not** tested.

### 6.3 Coding task — Attempt 1

- **Model:** `opencode/mimo-v2.6-flash-free`
- **Task:** implement the chess-specific context-window policy from `problem_statement.md`
- **Allowed source path:** `src/assignment/agent/chess_agent.py`
- **Credentials passed:** none
- **Runtime limit:** 1,200 seconds (20 minutes)
- **Result:** `RuntimeError: OpenCode run failed (exit 124)`
- **Patch:** **not generated/saved**; host ChessAgent source was unchanged

The runner raised on a nonzero command exit before writing the proposed patch/events artifacts. The full attempt did not, by itself, reveal the underlying provider error.

### 6.4 Short diagnostic — definitive provider error

A separate disposable sandbox invoked the same model with a trivial request: “Reply with exactly READY. Do not inspect or edit files.” The diagnostic included debug logs and a **90-second** command timeout.

- OpenCode session initialized, and `build` agent model selection succeeded.
- The provider returned:

```text
AI_APICallError: Free usage limit reached.
Free models work in OpenCode (https://opencode.ai);
subscribe to OpenCode Go to keep going: https://opencode.ai/go
```

- The title-generation request also encountered retries and the same free-usage-limit error.
- The command ultimately exited **124** due to the 90-second timeout, with no model response.
- The sandbox Git working tree was clean afterward; it was destroyed normally.

**Conclusion supported by evidence:** the attempted MiMo free-model request was blocked by the OpenCode provider's free usage limit. Docker, CLI installation, repo isolation, and the initial testbed were working. We cannot conclude that every free model is blocked, that a later retry will be blocked, or that another provider would fail.

### 6.5 Lessons and decisions

1. **Separate catalog discovery from real inference access.** Test a short prompt before a long coding task.
2. **Limit time and expose diagnostic output.** Preserve sanitized exit status, standard error, structured events, and provider-error messages even when a runner raises; avoid another silent 20-minute timeout.
3. **Keep coding-model costs and chess-evaluation costs distinct.** A free-labeled model may have quotas; API-backed models incur billable use.
4. **Reuse disposable Git-snapshot sandboxes.** Do not include private trajectories or credentials in Docker build contexts/images.
5. **Treat patch allowlisting as a validation step**, not a full sandbox permission mechanism; review a patch before applying it to the host.
6. **Preserve OpenCode integration** rather than replacing it; add another coding-agent path instead.

We decided **not to subscribe to OpenCode Go just to complete this experiment**. The next integration will try Codex CLI with our existing OpenAI Platform API account.

## 7. Next milestone — Step 54: Add Codex CLI as the third coding agent

**Agreed plan:** Keep original CodeAgent, retain OpenCode, and add a separate **Codex CLI** sandbox and runner. Initially use the Codespaces `OPENAI_API_KEY` already configured for the project, but inject it **only at runtime**, with a future move to a dedicated budget-limited API project/key. Codex API use may be billable; the ChatGPT subscription is not a substitute for API billing.

### 54A. Reopen and checkpoint the experimental branch

From the repository root:

```bash
git branch --show-current
git log -1 --oneline
git status --short
ls -l tasks/chess-context-window/
uv run pytest
```

Expect `experiment/chess-context-window`, a branch based on `9bed843`, and currently untracked `tasks/chess-context-window/`. Restore the updated `experiments/eval-harness/PROGRESS.md` on this branch, review it, and **commit the task definition, session notes, Dockerfile, and progress file** before further experiments. Push the experimental branch after confirming the intended files; never force-push to resolve routine divergence.

### 54B. Inspect Codex CLI before making a model request

1. Confirm a suitable pinned Codex CLI release, its runtime dependencies, and the **actual** noninteractive CLI flags using its documentation and `--help`. Do not assume OpenCode flags work in Codex.
2. Create a **Codex-specific Docker image/testbed** from a clean `git archive` snapshot; exclude local `artifacts/`, `.git`, `.venv`, secrets, and untracked data.
3. Verify installation and run `codex --version` and `codex exec --help` **without model calls**.
4. Verify the container starts with no OpenAI key. Use authenticated runtime injection only when making a deliberate model request; never bake secrets into a Dockerfile, image layer, Git commit, or logs.
5. Decide on model/API eligibility, cost limits, network/tool permissions, and timeouts *before* a full task. An isolated container with a shell and network access can potentially read runtime credentials; minimize what is exposed.

### 54C. Implement and offline-test a `CodexRunner`

Aim for a runner analogous to `OpenCodeRunner` while keeping both implementations:

- **Inputs:** clean testbed, task text, chosen coding model, allowed paths, timeout, authorized runtime credentials.
- **Execution:** Codex noninteractive coding task; collect structured events and terminal output, exit status, and (where available) usage/cost telemetry.
- **Outputs:** source diff/patch, changed paths, validation results, failure diagnostics, and execution metadata.
- **Controls:** reject paths outside the allowlist, refuse unexpected dirty baselines/overwrites, avoid host-code mutation, and preserve sanitized failure logs.
- **Offline regressions:** mock CLI execution; validate successful patch capture, rejected unauthorized paths, timeouts, nonzero exits, patch safety, and cleanup.

Prefer a **small smoke test** of API-key authentication first. Only then run the full chess-context-window coding task; keep it in a disposable sandbox. Do not automatically apply the generated patch to Codespaces.

### 54D. Return to the controlled chess-harness experiment

Once Codex produces a patch:

1. Review it against `tasks/chess-context-window/problem_statement.md`.
2. Verify that `full` behavior remains the default, latest-state prompts preserve a complete current chess state and linked tool messages, and unsafe sequences fall back correctly.
3. Add source-specific regression tests; run the full offline and Docker suites.
4. Make the experiment plan explicitly record `chess_agent.context_policy` (or an equivalent reproducible configuration). **Do not mistake the chess-application `--patch` mechanism for this Python harness change.**
5. Commit a verified harness revision before live evaluation.
6. Run controlled `gpt-5-mini` trials using the **same unpatched chess application**, 3 steps/trial, 3 trials, legal moves enabled, programmatic tools disabled.
7. Compare input tokens, total tokens, accepted moves, tool errors, failed trials, final positions, and prompt history. Treat three short trials as preliminary evidence only.

**Baseline 003 reference values:** mean **3,298 input tokens**, mean **3,628 total recorded tokens**, **9/9 accepted moves**, **0 tool errors**, **3/3 available reports**, **0 completed games**.

## 8. Backups, source control, and safe shutdown

**Tracked in Git:** source, tests, `experiments/eval-harness/baseline-003.json`, and the earlier uploaded `PROGRESS.md` at commit `cf7ae35`. This updated document must still be copied into the repository and committed. Current experiment task files are untracked until committed.

**Not tracked in Git:** raw trajectories, trial artifacts, backups, and other ignored local experiment outputs. Preserve them privately if they are important for continued research. An earlier raw baseline backup exists at `artifacts/backups/baseline-001-raw.tar.gz` with SHA-256:

```text
4c8228c5997bfbfffcf72e1c4ad4ab3d06027a7412e8ebbc5b3de2cf504a0f2a
```

Suggested private backup (verify paths exist first):

```bash
mkdir -p artifacts/backups
[ ! -d artifacts/eval-harness ] || \
  tar -czf artifacts/backups/eval-harness-checkpoint.tar.gz artifacts/eval-harness

git status --short
```

Download any important ignored files before **deleting** a Codespace. Stopping and restarting the *same* Codespace normally preserves its filesystem; deleting it does not. Never commit raw sensitive prompts, API secrets, or secret-bearing terminal logs.

---

**Suggested next-session message:**

> Continue CMU 11-768 at **Step 54** using `experiments/eval-harness/PROGRESS.md`. We're on `experiment/chess-context-window`, branched from baseline commit `9bed843`. Baseline 003 completed three real trials (3,628 mean total action tokens; 3,298 input tokens; 9/9 accepted moves). The OpenCode 1.19.2 MiMo free-model attempt failed because its provider reported **Free usage limit reached**; no patch was applied. Keep CodeAgent and OpenCode, and **add Codex CLI as a third coding agent in a clean Docker sandbox**, initially using our existing OpenAI API key with careful runtime-only credential handling. Start with Git checkpointing, a non-billable Codex CLI installation check, then implement and test `CodexRunner`, one step at a time.
