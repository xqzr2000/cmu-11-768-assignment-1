# Codex CLI Exploration: A Retrospective

**Date:** November 5, 2026  
**Repository:** [xqzr2000/cmu-11-768-assignment-1](https://github.com/xqzr2000/cmu-11-768-assignment-1)  
**Exploration branch:** `feature/codex-sandbox` (retired as a development direction, never merged into `main`, and **deleted** on November 9, 2026. This document is the record.)  
**Scope:** An independently developed third coding-agent backend for an adapted CMU 11-768 Assignment 1 project  
**Decision:** Archive the findings, preserve the stable Assignment 1 implementation, and stop investing in this Codex-specific integration.

> **Outcome in one paragraph.** The experiment **succeeded narrowly**: after debugging provider, sandbox, runner, and task-specification problems, an authenticated Codex CLI run produced a six-line patch that passed the original chess tests and **4/4 independent repair checks**. It **did not** demonstrate better chess play, fewer chess-agent tokens, or an improvement to the current branch, which already contained an equivalent fix. Codex's normal nested Linux sandbox could not run under our Docker restrictions, so the successful run used `danger-full-access` **inside** the Docker container with API access. That worked functionally but left credential/egress risks and additional maintenance burden. We therefore treat the integration as a completed learning experiment, not a feature to merge.

## 1. Research question and starting point

The project began as an adaptation of [CMU Assignment 1](https://github.com/cmu-agents/assignment-1): implement a reusable ReAct harness for coding and chess agents, replacing Modal execution with our own Docker sandbox in GitHub Codespaces. On `main`, we already had a `CodeAgent`, `ChessAgent`, context compaction, tool dispatch, regression tests, and a deterministic evaluation harness for chess trajectories.

Our extension asked: **Can a separate coding agent inspect a recorded harness failure, propose a small patch, and have that patch independently checked before we consider changing the harness?** The roles are distinct:

- **Chess-playing agent:** `ChessAgent`, using `gpt-5-mini` in recorded baseline trials. It plays chess; its outcomes and token usage are what a later chess improvement experiment would need to measure.
- **Harness-development agents:** the original `CodeAgent`, OpenCode, and the proposed Codex CLI backend. These edit harness source, not chess positions.
- **Evaluator:** deterministic Python regression checks and task-specific fail-to-pass/pass-to-pass checks, rather than an LLM's subjective claim that a patch succeeded.

The pre-existing [Baseline 003](../experiments/eval-harness/baseline-003.json) consisted of three `gpt-5-mini` trials, three model steps each, nine accepted moves, zero tool errors, and no completed games. It was a reproducibility checkpoint, **not** evidence of strong chess play.

## 2. Why we moved from OpenCode's free model to Codex CLI

Our earlier [OpenCode trajectory-logging experiment](../tasks/chess-trajectory-logging/experiment-records/SESSION_NOTES.md) showed that feedback could improve a generated repair: the second candidate passed **2/2 fail-to-pass**, **1/1 pass-to-pass**, and **3/3 targeted public** checks.

We next asked OpenCode to implement a chess-specific context-window policy. The tested model was `opencode/mimo-v2.6-flash-free`. The full coding attempt timed out after 1,200 seconds and yielded **no saved patch**. A separate short diagnostic with the same provider/model established the decisive issue: **`AI_APICallError: Free usage limit reached`**. We verified that the CLI and disposable Docker testbed worked; we did **not** establish that all OpenCode free models were unusable, nor that the problem was with our sandbox.

Rather than subscribe to OpenCode Go just for this experiment, we retained `OpenCodeRunner` and explored **Codex CLI as a third, optional coding-agent backend** using our existing OpenAI Platform API access. This was a deliberate trade: known paid inference and more engineering control instead of depending on an uncertain free-provider quota.

## 3. What we built to make Codex work

The implementation on `feature/codex-sandbox` went beyond installing another CLI.

| Layer | What we implemented or verified | Why it mattered |
| --- | --- | --- |
| Reproducible image | `tasks/codex-harness-improvement/Dockerfile` pinned Codex CLI **0.166.0** in a Python 3.12 Docker task image | Keep CLI behavior and task dependencies identifiable |
| Disposable testbed | Build from a clean Git snapshot; run Codex against an isolated `/testbed`; exclude private artifacts and host `.git` state | Avoid editing the Codespace working tree during candidate generation |
| Runner | `src/assignment/codex_runner.py`: explicit model, timeout, clean-tree preflight, CLI-version check, JSONL events, Git diff extraction | Require observable execution and a reviewable artifact |
| Patch review | Only permit the task's allowed source file (`src/assignment/agent/chess_agent.py`); reject unexpected changes, deletion, symlink substitution, and directly detectable secret leakage | Reject invalid **outputs**, without pretending to prevent unsafe runtime actions |
| Offline verification | `scripts/verify_codex_sandbox.py` checked the CLI, clean Git state, absent API key/private artifacts, nine original chess tests, and container cleanup | Prove installation and isolation without spending model tokens |
| Experiment driver | `scripts/run_codex_chess.py` checked historical task provenance, ran at most one authorized model attempt, reviewed/extracted a patch, ran original regressions, and independently graded the candidate | Distinguish model completion from actual task resolution |
| Diagnostics | `src/assignment/codex_diagnostics.py` and `scripts/diagnose_codex_experiment.py`, with focused unit and Docker tests | Capture nested failures and preserve bounded, sanitized evidence |
| Secrets and network | Changed Docker command-scoped environment forwarding so key **values** were not placed in Docker command-line arguments; added selectable Docker `network="none"` for offline tests | Reduce one credential exposure path and permit network-free diagnostics |

The original sandbox runtime dropped Linux capabilities, used `no-new-privileges`, imposed resource/time limits, and did not intentionally mount the host Docker socket into task containers. These controls were useful, but **they did not make a network-connected, model-driven execution container a hardened security boundary**.

### The nested-sandbox compatibility problem

Unlike OpenCode's workflow, Codex CLI tried to create an **inner** Linux sandbox (using `bubblewrap`) inside our already restricted Docker container. In the Codespaces/Docker configuration used for this experiment, it failed with namespace-permission errors; one diagnostic reported `bwrap: No permissions to create a new namespace`, and a seccomp-relaxed diagnostic still encountered UID-map permission failure.

Simply making the outer container privileged or disabling its security restrictions would have defeated the reason for building a controlled sandbox. We did **not** adopt that approach.

Instead, the runner supported an explicitly selected `danger-full-access` mode **for Codex's inner execution**, while leaving the outer Docker restrictions in place. This allowed the repair workflow to run. It did **not** solve the important residual issue: the Codex process and its launched commands could operate within the container while an API credential was available and bridge networking permitted outbound requests. Post-run source allowlisting cannot prevent actions taken **before** the patch is collected. Running the container with `network="none"` worked for offline diagnostics but could not directly reach the model API.

### The runner and diagnostic issues

Two different types of event must not be conflated: a nonzero/failed tool command, a **nonfatal** nested CLI notice, and a genuine top-level `error` or `turn.failed`. Early versions of our runner either missed internal command failure when the CLI exited 0 or rejected completed work because a nested `item.completed` event had type `error`. After inspecting Codex 0.166.0's event behavior, we treated supported nested notices as warnings, kept fatal top-level events fatal, and preserved sanitized diagnostics for rejected results.

We also found that `gpt-5.3-codex` was not represented in the pinned CLI's bundled model metadata. A fallback warning appeared, and a native patch-tool integration was unavailable in one observed run; an attempted shell `apply_patch` returned exit 127 before Codex recovered using another method. Authentication and a completed process did not by themselves guarantee a valid coding toolchain.

## 4. Live results: failures, correction, and one resolved repair

Three paid repair attempts were recorded on November 5, 2026 UTC. All used **`gpt-5.3-codex`**, CLI **0.166.0**, and a **600-second** limit.

| Run ID suffix | Observed result | Lesson |
| --- | --- | --- |
| `043026732054Z` | Codex produced a patch, but the then-current runner rejected it after a nonfatal nested notice. | Record and classify warning events correctly; retain validated-but-rejected artifacts |
| `045045710764Z` | Patch passed original tests and 2/2 pass-to-pass checks, but failed 2/2 fail-to-pass checks. The emitted error omitted the word `stale` expected by the grader. | Align task wording with literal test expectations; distinguish specification mismatch from behavioral error |
| `052720929149Z` | **Success:** accepted and validated patch, original chess tests passed, **2/2 fail-to-pass + 2/2 pass-to-pass checks passed**, `resolved: true`. | A complete patch → regression → independent-grader workflow was feasible |

The successful candidate modified **only** `src/assignment/agent/chess_agent.py`, adding **six lines**. It rejected a `simulate_move` that followed a board-changing `play_move` or `run_python` in the *same* assistant response, explaining that the simulated position was **stale**. Earlier simulations remained allowed, each new response reset the guard, and the original `tool_call_id` was retained.

**Critical qualification:** the generated patch targeted historical task base commit **`86cd65a22439f52d58545eda53fbf3c1be9bcb6e`**. The development branch **already contained a functionally equivalent stale-position guard**, so the six-line historical patch was **not reapplied** to the branch. The successful run proved one coding-agent repair benchmark; it did **not** produce an additional improvement to the current harness.

The recorded successful run used **62,985 input tokens** (of which **59,008 were cached**, not additional), and **1,029 output tokens**. It also reported one nonfatal nested warning and zero top-level errors. These are token telemetry, **not a verified dollar cost**. Post-run targeted chess-agent and tool-ordering tests passed **9/9**. An earlier feature-branch [GitHub Actions run](https://github.com/xqzr2000/cmu-11-768-assignment-1/actions/runs/41972053570) passed both unit and Docker jobs.

The structured paid-run records and diffs were kept privately in the Codespace under `.private/codex-runs/`; raw events and stderr should **not** be committed because redaction is best-effort and may miss secrets or sensitive prompt content.

## 5. Why we are ending the feature exploration

The stop decision is about **research value and acceptable risk**, not a claim that Codex cannot write working code.

1. **The narrow proof of concept is complete.** The historical repair passed its independent evaluator. Repeating it does not answer a new question.
2. **We did not demonstrate the intended downstream benefit.** There was no controlled before/after chess-agent evaluation showing reduced context tokens, better decisions, more completed games, or better error recovery. A coding agent's patch score is not a chess-agent performance result.
3. **The most practical live configuration has unresolved security assumptions.** Codex's inner sandbox failed under our outer Docker restrictions. `danger-full-access` inside network-connected Docker made execution possible but left credential and egress exposure to address. Docker isolation and a patch allowlist alone are insufficient.
4. **The integration accumulated disproportionate complexity.** We added a new CLI pin, Docker image, runner, event parser, diagnostic utility, credential-forwarding behavior, network controls, and many tests to support a single narrow benchmark. Model metadata and event semantics also depend on CLI version.
5. **Paid retries and high token usage need a stronger payoff.** We had multiple paid attempts, including one rejection caused by our own event handling and one failure caused by task wording. Future runs should have a clear measurable hypothesis before incurring more costs.
6. **Assignment 1 completion has higher priority.** The stable `main` branch already contains the ReAct/Docker/chess evaluation foundation. Missing official run artifacts and analysis reports are a more direct next milestone than integrating a third coding-agent backend.

**Decision:** Do not merge the Codex-specific feature into `main` merely because one historical task resolved. Preserve this report as the durable record. Retire `feature/codex-sandbox` separately once the report is verified on `main` and any private evidence worth keeping is backed up.

## 6. Lessons worth carrying forward

- **Availability is not inference access.** A free-labeled model appearing in a catalog does not guarantee usable quota. Probe a small request before launching a long coding task.
- **Outer and inner sandboxes can conflict.** More layers are not automatically safer or more reliable. Test the exact nested execution path early.
- **Permission settings and isolation are different.** `danger-full-access` changes Codex's execution policy; Docker still defines the outer boundary. Neither eliminates credential/network risk.
- **Secrets should not be embedded in images, Git commits, or command arguments.** Passing values through a subprocess environment is an improvement, not perfect secret isolation.
- **An exit code of zero is weak evidence.** Inspect tool events, source changes, tests, and independent grade results. Preserve useful diagnostics on rejected candidates without leaking sensitive data.
- **Good evaluations must be specified clearly.** The missing word `stale` exposed an accidental mismatch between a reasonable implementation and an overly literal test requirement.
- **Separate three kinds of success.** (1) Codex runs, (2) Codex produces a verified patch, (3) the changed harness demonstrably improves agent behavior. We established the first two for one historical task, **not** the third.
- **Use a stop rule.** Once the proof of concept is achieved and remaining work is mostly platform hardening or repeated diagnosis, return to the primary assignment rather than letting infrastructure work become the goal.

## 7. Archival record and boundaries

This document is intentionally a **retrospective**, replacing the feature branch's long running `experiments/eval-harness/PROGRESS.md` handoff log. It summarizes observed evidence and the final decision; it is **not** a runbook instructing anyone to spend tokens recreating the experiment.

**Relevant implementation paths on the exploration branch (not intended for merge):**

- `src/assignment/codex_runner.py` and `src/assignment/codex_diagnostics.py`
- `tasks/codex-harness-improvement/Dockerfile`
- `scripts/verify_codex_sandbox.py`, `scripts/run_codex_chess.py`, `scripts/diagnose_codex_experiment.py`
- `tests/test_codex_runner.py` and related targeted tests
- `packages/agent-sandbox-runtime/src/agent_sandbox_runtime/{process.py,sandbox.py}` (credential-forwarding changes)

**Reproducibility markers:** historical task commit `86cd65a`; original integration commits `5c3a367` and `e0b90bc`; nested sandbox/runner development commits `789784d`, `eeaa0d8`, `638fb41`, `b9adf2a`; successful private run ID `codex-chess-20261105T052720929149Z`. Git commit IDs are historical evidence identifiers. The branch has been deleted (last tip `746f015`), so these feature-only commits are no longer on any branch and may become unavailable.

**Retain:** the report committed to `main`, the independent stable Assignment 1 evaluation baseline, and any locally backed-up, appropriately sanitized records needed for private audit. **Do not retain in public Git:** API keys, raw paid-run event logs/stderr, or sensitive private artifacts. **Do not infer:** production-grade safety, successful context-window optimization, or improved chess-playing performance.

### Final assessment

**Codex CLI worked as a bounded coding agent in our disposable Docker testbed after significant adaptation. It was a useful engineering lesson but not a justified feature to carry forward now.** The durable value is the clearer model of sandbox composition, credential exposure, event correctness, evaluator quality, and the discipline of measuring downstream agent outcomes before expanding infrastructure.
