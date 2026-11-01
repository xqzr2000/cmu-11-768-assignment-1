# CMU 11-768 — Evaluation Harness Progress and Session Handoff

**Checkpoint:** Step 45 complete (session ending 2026-11-01 UTC / 2026-10-31 Pacific)  
**Repository:** `xqzr2000/cmu-11-768-assignment-1`  
**Branch:** `experiment/eval-harness`  
**Latest verified commit:** `24a03bc` — `Enable multi-trial chess experiments from CLI`  
**Git state at checkpoint:** clean; branch pushed to `origin/experiment/eval-harness`  
**Next step:** **Step 46 — First real three-trial unpatched baseline**

> **Resume here:** The multi-trial CLI is implemented and mock-tested, but a real multi-trial execution has **not yet** been run. First confirm Codespaces/Docker/API readiness, then run `baseline-unpatched-003` and inspect the results. Expect billable OpenAI API usage.

## 1. Project objective

Adapt CMU 11-768 Assignment 1 into a reproducible, local experiment loop:

1. Run a chess agent in an isolated Docker sandbox (hosted inside GitHub Codespaces, rather than requiring Modal).
2. Record agent trajectories, actions, observations, outcomes, and token usage.
3. Evaluate trials offline with deterministic Python metrics, not an LLM judge.
4. Repeat and aggregate baseline trials to estimate reliability and variability.
5. Later use **OpenCode** in its own sandbox to propose chess-harness changes, then compare patched and unpatched runs under controlled settings.

The **chess-playing model** is `gpt-5-mini` via the OpenAI API. The model used by **OpenCode** to *develop* harness changes is a separate concern; OpenCode is **not** involved in the next baseline run.

## 2. Completed and verified

| Component | Implementation | Evidence / status |
|---|---|---|
| Local sandbox and chess agent | Repository sandbox runtime, `ChessSandbox`, `ChessAgent` | Earlier Docker integration tests passed |
| Offline trajectory evaluation | `scripts/eval_chess_trajectory.py` | Regression-tested |
| Compare two trial evaluations | `scripts/compare_chess_evaluations.py` | Regression-tested; single-run comparison is not proof of improvement |
| Experiment planning and guarded single-trial execution | `scripts/run_chess_experiment.py` | One real unpatched trial completed to step limit |
| Offline aggregation of multiple trials | `scripts/aggregate_chess_trials.py` | 10 dedicated tests passed |
| Resilient multi-trial orchestration | `execute_experiment()` in `scripts/run_chess_experiment.py` | 13 batch tests passed; mocked failure in trial 2 did not prevent trial 3 |
| Multi-trial CLI dispatch | `--trials N --execute` in `scripts/run_chess_experiment.py` | 10 CLI tests passed, including batch dispatch/failure/existing-output protection |

**Final suite at checkpoint:** `uv run pytest` → **105 passed, 3 deselected**. The three deselected tests are Docker-marked; they were passed in an earlier session but **were not rerun in this final checkpoint**.

Recent commits (newest first):

```text
24a03bc Enable multi-trial chess experiments from CLI
19a5a64 Add resilient multi-trial chess experiment orchestration
9be374d Add offline chess trial aggregation and regression tests
983691c Record first automated chess evaluation baseline
1601d77 Add guarded chess experiment CLI and integration tests
```

## 3. Baseline evidence so far

| Experiment | Mode | Outcome | Accepted moves | Recorded action tokens |
|---|---|---|---:|---:|
| `baseline-001` | Earlier manual single trial | Step limit, game not complete | 3 | 4,272 |
| `baseline-unpatched-002` | Automated single trial | Step limit, game not complete | 3 | 3,754 |
| `baseline-unpatched-003` | Planned three trials | **Not run** | — | — |

The first two trials both accepted three moves and did not finish a chess game. The 518-token difference (about 12.1%) is **not evidence of harness improvement**: these are two single runs, and the harness was not experimentally changed between them. A three-step trial is useful for execution reliability and telemetry, not a measure of full-game chess strength.

The tracked summary records include `experiments/eval-harness/baseline-001.json` and `experiments/eval-harness/baseline-002.json`. Detailed run artifacts are under `artifacts/eval-harness/` and intentionally Git-ignored. Earlier private raw backup: `artifacts/backups/baseline-001-raw.tar.gz` (SHA-256: `4c8228c5997bfbfffcf72e1c4ad4ab3d06027a7412e8ebbc5b3de2cf504a0f2a`). Do not commit raw trajectories, API keys, or private backups.

## 4. Step 46 — Resume in GitHub Codespaces

### A. Verify repository and environment

From the repository root:

```bash
git branch --show-current
git status --short
git log -1 --oneline

# Confirm local Docker and chess prerequisites.
make sandbox-doctor
make doctor

# Verify offline regressions.
uv run pytest

# Optional but recommended before the first live batch:
uv run pytest -m docker -v

# Verify that an API key is present WITHOUT printing the secret.
test -n "${OPENAI_API_KEY:-}" && echo "OPENAI_API_KEY present" || echo "OPENAI_API_KEY missing"
```

Expected branch: `experiment/eval-harness`; expect a clean working tree and 105 passing offline tests (unless tests have changed since this checkpoint). The live runner requires a clean Git tree. **If this progress file is newly added to the repository, commit and push it before executing the live run.** That documentation commit will become the new `harness_commit` recorded in subsequent plans; it does not imply an agent harness code change.

### B. Review the planned experiment without model calls

```bash
uv run python scripts/run_chess_experiment.py \
  --experiment-id baseline-unpatched-003 \
  --model gpt-5-mini \
  --step-limit 3 \
  --trials 3 \
  --unpatched \
  --dry-run
```

Confirm the configuration is correct and no prior outputs exist for this experiment ID.

### C. Execute the real three-trial baseline (billable)

**Only after preflight checks pass:**

```bash
uv run python scripts/run_chess_experiment.py \
  --experiment-id baseline-unpatched-003 \
  --model gpt-5-mini \
  --step-limit 3 \
  --trials 3 \
  --unpatched \
  --execute
```

This should launch trials sequentially with separate sandboxes, up to three model steps per trial (at most nine planned model steps). It will call the OpenAI API. Keep Codespaces active until the run finishes. Do not assume all three trials will succeed; the CLI returns a nonzero exit status if the batch has unexpected failures, while attempting to retain a summary.

**Do not rerun the same `experiment-id` blindly.** The runner is designed to refuse existing output files. Use a new ID for a new run; preserve evidence of failures.

### D. Inspect and validate outcomes

Expected output directory: `artifacts/eval-harness/baseline-unpatched-003/`.

```bash
ls -lh artifacts/eval-harness/baseline-unpatched-003/

uv run python -m json.tool \
  artifacts/eval-harness/baseline-unpatched-003/summary.json

# Independently recompute aggregation from saved trial artifacts.
uv run python scripts/aggregate_chess_trials.py \
  artifacts/eval-harness/baseline-unpatched-003/plan.json
```

Check: `planned_trials`, `reports_available`, `report_coverage`, `outcomes`, accepted moves, tool errors, token-usage coverage, and `game_over` for each trial. Then inspect each trial's trajectory for the move sequence and any tool failures. **Do not mistake `step_limit` for a completed chess game or a failed infrastructure run.**

**Important:** `scripts/compare_chess_evaluations.py` compares individual evaluation reports; do not pass an aggregated `summary.json` to it without first extending the comparator to support experiment summaries.

## 5. After Step 46

1. Record a small, tracked summary of `baseline-unpatched-003` (configuration, aggregate metrics, any problems, and the current commit), keeping raw traces ignored.
2. Examine across-trial variation in accepted moves, failures, token counts, and exact chess moves. Report missing data separately from successful metrics.
3. Review comparability: same chess environment, agent model, prompts, tool interface, step limit, and harness changes across experiments. Record configuration and commit differences explicitly.
4. Once the unpatched repeated baseline is working, construct a controlled OpenCode-proposed patch experiment and evaluate it with the same protocol. Avoid claims of chess-strength improvement based only on three model steps.
5. Consider a longer and more informative chess benchmark after the orchestration smoke test, with enough independent trials to estimate variability.

## 6. Backups and safe shutdown

Code and tracked records are already on GitHub at commit `24a03bc` as of this checkpoint; local ignored outputs are **not** backed up by `git push`.

```bash
mkdir -p artifacts/backups

tar -czf artifacts/backups/eval-harness-checkpoint.tar.gz \
  artifacts/eval-harness

# Verify status before stopping Codespaces.
git status --short
```

Download the checkpoint archive (and retain the earlier `baseline-001-raw.tar.gz`) to a private location before deleting a Codespace. Stopping and restarting the *same* Codespace normally retains its filesystem; deleting it does not. Stop, rather than delete, the Codespace when done.

---

**Next-session prompt:** "Continue CMU 11-768 evaluation harness from Step 46. On branch `experiment/eval-harness`, Step 45 committed at `24a03bc`. First verify Codespaces prerequisites and the 105-test offline suite, then run and inspect the first real three-trial unpatched baseline `baseline-unpatched-003`, one step at a time."
