# Russell's Take on CMU 11-768 Assignment 1

> Building an AI agent harness with Docker, OpenAI-compatible model APIs (DeepSeek and OpenAI), and OpenCode to understand and improve agent systems. I am a student at Pitt and am not registered at CMU for any academic credit.

A hands-on adaptation of [CMU 11-768 Assignment 1: Build an Agent Harness](https://github.com/cmu-agents/assignment-1), developed to study how AI agents interact with tools, execute code safely, maintain context, and improve their performance through evaluation feedback.

This project replaces the original assignment's Modal execution infrastructure with a reusable Docker sandbox running inside GitHub Codespaces. It also extends the assignment with OpenCode-driven harness improvement experiments and trajectory- and telemetry-based analysis.


## Current snapshot (November 9, 2026)

**Status: all three parts of Assignment 1 have been built, run and analysed for learning** (not for credit). The agents ran on DeepSeek-V4.1-Flash, plus gpt-5-mini as the second model in the observation experiment, in our own Docker sandbox. The one requirement deliberately skipped is a *finished* chess game.

| Part | Result | Details |
| --- | --- | --- |
| **1. Coding agent repairs the chess app** | ✅ Resolved: FAIL_TO_PASS 1/1, PASS_TO_PASS 9/9 in 13 steps. Repeated 3/3 in a comparison | [§8](#8-running-the-coding-agent) |
| **2. Context compaction on SWE-bench `django__django-15368`** | ✅ The compacted and full-context runs both resolved (1/1 + 29/29). 2 compactions, −25% total tokens but 2.6× more *uncached* tokens | [§9](#9-context-compaction-and-swe-bench), [token report](docs/reports/token-usage-analysis.md) |
| **3.2 Observation A/B (board only vs + legal moves)** | ✅ 4 runs × 15 steps: gpt-5-mini 20% → 0% illegal moves; DeepSeek 0% → 0%, but it thought 6× longer with the list | [§10](#10-running-the-chess-agent), [observation report](docs/reports/observation-experiment.md) |
| **3.4–3.5 Programmatic tools + skill** | ✅ `invoke_skill` → `run_python` searching with `simulate_move` → one `play_move` per snippet | [§10](#10-running-the-chess-agent) |
| **3.1 Basic game to a terminal state** | ⏭️ Skipped by choice after two partial games. One reached a winning K+Q vs K+B before the sandbox expired | [§10](#10-running-the-chess-agent) |

| Extension | Result |
| --- | --- |
| Harness fixes found by running the agents | A circuit breaker for a lost chess server, a duplicate `invoke_skill` tool, OpenCode quota errors misreported as timeouts, and an API-key leak path in the OpenCode runner |
| CodeAgent vs OpenCode on Part 1 | CodeAgent 3/3. OpenCode's free tier refused every request ("Free usage limit reached"), so no OpenCode trials ([write-up](docs/Coding-Agent-Comparison.md)) |
| Harness² | Explored and dropped ([§13](#13-why-we-did-not-adopt-harness)) |

**Tests:** 138 non-Docker tests pass (`uv run pytest`) and 3 Docker integration tests pass (`make test-docker`) on `main` as of Nov 9. Run artifacts live in the Git-ignored `artifacts/` folder, so they are summarised here and in the reports rather than committed.

**Where to read more:** [`docs/Learning-Progress.md`](docs/Learning-Progress.md) is the full learning log: requirements, adaptations, every run and its numbers, and the lessons. [Section 15](#15-current-state-completed-work-adaptations-and-open-gaps) summarises the status, and [Section 17](#17-optional-next-steps) lists optional follow-ups.

---

## 1. Project overview

An AI agent is more than a language model. It needs a *harness*: software that lets the model observe its environment, select tools, perform actions, receive results, and continue working toward a goal.

This project explores five connected capabilities:

1. **Agent orchestration:** Implement a reusable ReAct loop for coding and chess agents.
2. **Sandboxed execution:** Run agent-generated commands inside isolated Docker containers.
3. **Context management:** Compact long interaction histories while preserving useful working memory.
4. **Tool-based reasoning:** Use chess tools, programmatic actions, and reusable agent skills.
5. **Harness improvement:** Analyze trajectories and use OpenCode to propose, test, and refine changes to the agent harness.

The first four capabilities originate from the CMU assignment or its supporting architecture. The fifth is our independent extension.

### Technology stack

| Component           | Technology                               | Purpose                                                  |
| ------------------- | ---------------------------------------- | -------------------------------------------------------- |
| Development         | GitHub Codespaces / VS Code              | Reproducible cloud development environment               |
| Language            | Python 3.12                              | Agent orchestration, evaluation, and sandbox integration |
| Dependencies        | `uv` workspace                           | Manage the assignment and sandbox-runtime packages       |
| Model inference     | OpenAI-compatible API (DeepSeek, OpenAI) | Generate agent actions and reasoning                     |
| Sandbox runtime     | Docker                                   | Execute untrusted task commands in disposable containers |
| Coding agent        | `CodeAgent`                              | Repair software and solve coding tasks                   |
| Chess agent         | `ChessAgent`                             | Play chess using tools and programmatic actions          |
| Coding assistant    | OpenCode (free models, no API key)       | Harness-repair experiment; coding-agent comparison       |
| Testing             | pytest and GitHub Actions                | Check functionality and regressions                      |
| Evaluation evidence | JSON trajectories and experiment records | Investigate outcomes and compare candidate changes       |


## 2. Original CMU Assignment 1 requirements

The original assignment was developed for Carnegie Mellon University's 11-768 course on AI agents.

**Official repository:** [cmu-agents/assignment-1](https://github.com/cmu-agents/assignment-1)

**Original requirements:** [ASSIGNMENT.md](https://github.com/cmu-agents/assignment-1/blob/main/ASSIGNMENT.md)

The original project contains three main parts.

### Part 1 — Build a coding agent

Implement a reusable ReAct agent that can interact with a terminal environment to solve software problems.

Major requirements include:

- Construct structured prompts containing system instructions, user tasks, assistant actions, and tool observations.
- Implement the agent's reasoning-and-action loop.
- Execute coding tools and return their observations to the model.
- Handle malformed arguments, unknown tools, and execution errors.
- Support reusable agent skills through progressive disclosure.
- Repair a bug in a chess application and submit the resulting patch.

The coding agent is expected to produce a patch that can be applied and independently tested.

### Part 2 — Implement context compaction

As an agent works, its conversation and tool history grow.

The assignment introduces context compaction to reduce the active prompt size while retaining information necessary to continue the task.

The agent must preserve relevant objectives, constraints, completed work, failed attempts, important observations, and next actions.

The original exercise uses a SWE-bench coding task to investigate how context compaction affects token usage and agent behavior.

### Part 3 — Build a chess-playing agent

Reuse the base agent loop to create `ChessAgent`.

The chess agent plays White against a deterministic chess bot, interacting with the application through tools rather than directly modifying the game state.

The assignment introduces:

- `play_move`: Execute a legal move using UCI notation.
- `simulate_move`: Explore a possible move without changing the live game.
- `run_python`: Execute model-generated Python that can call registered chess tools.
- `invoke_skill`: Load reusable chess-playing instructions.

The assignment also explores how different tool observations affect agent behavior, including the difference between providing a board alone and providing a board with legal moves.

### Original execution infrastructure

The original assignment uses Modal to execute agent-generated code inside remote sandboxes.

Modal supplies managed execution infrastructure. The agent harness, model API calls, task definitions, and evaluation procedures remain separate concerns.

Our project preserves that separation while replacing the execution backend.

---

## 3. Our independent adaptation

The central architectural change is:

**Original:** Agent → Modal environment → remote sandbox

**Adapted:** Agent → `Environment` adapter → local Docker runtime → disposable task container

### Adaptations at a glance

| Original Assignment 1 | Our adaptation on `main` | Why |
| --- | --- | --- |
| Modal-managed execution environments | `assignment.env.Environment` backed by `agent_sandbox_runtime` and Docker | Inspect and control sandbox lifecycle locally in Codespaces |
| Course-provided DeepSeek-V4-Flash endpoint; DeepSeek vs GPT-OSS-120b A/B | Configurable OpenAI-compatible client: `deepseek-flash` (DeepSeek-V4.1-Flash) via DeepSeek's API; gpt-5-mini (OpenAI) as the second A/B model | Run independent experiments with our own API accounts |
| Course-oriented source/testing flow | `uv` workspace, pinned chess source bootstrap, Docker and GitHub Actions tests | Reproduce the environment and catch regressions without a Modal account |
| ReAct loop, CodeAgent, compaction and ChessAgent | Original agent abstractions preserved, with Docker-specific adapters | Keep the focus on agent behavior rather than replacing the whole harness |
| No general repeated-trial chess evaluation in the assignment workflow | Offline trajectory scorer, experiment runner, trial aggregation, committed summaries | Measure observed behavior and provide reproducible evidence |
| No external harness-development coding agent required | Optional OpenCode-based repair experiment | Test whether feedback can improve the harness itself |
| — | CodeAgent vs OpenCode (free model, never a paid API) comparison on Part 1 | Separate the harness's contribution from the model's |

The later Codex CLI work remains on `feature/codex-sandbox`; it is **not** part of this table's `main` implementation. Model/API changes and Docker execution are independent choices. Neither should be presented as satisfying the original course's exact model or Modal-specific grading requirements automatically.

We retain the agent-oriented architecture while making the execution infrastructure independently reproducible.

### Why replace Modal?

*I like Modal's service. My take on Stanford's CS336 uses their H100s to train GPT-2.*

Modal is a useful managed sandbox platform, but it introduces another external service and account dependency.

For independent learning, we wanted to:

- Run the full execution stack inside GitHub Codespaces.
- Understand how a sandbox is constructed and managed.
- Inspect the commands sent into the sandbox and the results returned.
- Control Docker images, execution timeouts, ports, and cleanup.
- Reduce dependency on third-party sandbox services.
- Reuse the runtime for chess agents, coding agents, and future evaluation experiments.

This does not eliminate all external dependencies. GitHub Codespaces provides the development compute, and OpenAI API calls may incur charges. However, this eliminates the need for a Modal account to run our adapted execution workflow and puts the sandbox back under my own control. The sandbox is needed for OpenCode anyway.


## 4. System architecture

The project separates model inference, agent orchestration, and task execution.

```
GitHub Codespaces
|
|-- Python agent process
|   |
|   |-- CodeAgent / ChessAgent
|   |-- Shared ReAct loop
|   |-- Context compaction
|   |-- Tool dispatch
|   |-- Trajectory logging
|   |
|   |-- OpenAI-compatible API
|   |   └─- Remote model inference
|   |
|   └─- assignment.env.Environment
|       |
|       └─- agent_sandbox_runtime.Sandbox
|           |
|           └─- Docker engine
|               |
|               └─- Disposable task container
|                   |-- Coding task files
|                   |-- Chess application
|                   |-- Shell and Python
|                   |-- Tests
|                   └─- Agent-generated commands
|
└─- OpenCode experiments
    |
    |-- Isolated development task
    |-- Proposed harness patch
    |-- Regression evaluation
    └─- Experiment records
```

### Is this Docker-in-Docker? Yes, *Docker Inception!*

The Codespaces development environment is configured with the Docker-in-Docker devcontainer feature.

The project executes Python inside the development container. Its sandbox package uses the available Docker engine to build and launch separate task containers.

The important distinction is that the sandbox Python package is **not** another server or another language model.

It is a runtime library responsible for controlling Docker execution.

The OpenAI API remains outside the task container and handles model inference.

### Sandbox isolation

Agent-generated commands execute inside disposable containers rather than directly inside the agent's Python process.

Our implementation includes lifecycle management, command execution, timeout handling, and loopback-based access to the chess application.

This provides a useful isolation boundary for experiments, but Docker containers are not a perfect security boundary against hostile code. Their security depends on daemon configuration, privileges, mounts, networking, and host isolation.

The runtime should be used for controlled development experiments, not treated as a hardened multi-tenant production security system.

## 5. Repository structure

The project is organized as a single `uv` workspace containing the assignment package and a reusable sandbox-runtime package.

```
cmu-11-768-assignment-1/
|
|-- .devcontainer/
|   |-- devcontainer.json
|   └─- post-create.sh
|
|-- .github/workflows/
|   └─- Automated tests
|
|-- packages/
|   └─- agent-sandbox-runtime/
|       |-- src/agent_sandbox_runtime/
|       └─- tests/
|
|-- src/assignment/
|   |-- agent/
|   |-- eval/
|   |-- cli.py
|   |-- env.py
|   |-- chess_sandbox.py
|   |-- chess_server.py
|   |-- sandbox_python.py
|   └─- task.py
|
|-- scripts/
|   |-- bootstrap_sources.sh
|   |-- bootstrap_chess_harness.sh
|   |-- evaluate.py
|   |-- evaluate_swebench.py
|   └─- ...
|
|-- tasks/
|   |-- chess-terminal-move/
|   |-- chess-harness-improvement/
|   |-- chess-trajectory-logging/
|   |-- code-skills/
|   |-- chess-skills/
|   └─- swebench/
|
|-- tests/
|
|-- .env.example
|-- Makefile
|-- pyproject.toml
|-- uv.lock
└─- README.md
```

Key components:

| Path                               | Responsibility                                    |
| ---------------------------------- | ------------------------------------------------- |
| `src/assignment/agent/`            | Shared agent logic and domain-specific agents     |
| `src/assignment/env.py`            | Compatibility adapter between agents and Docker   |
| `src/assignment/chess_sandbox.py`  | Chess application lifecycle and HTTP interface    |
| `src/assignment/sandbox_python.py` | Sandboxed Python execution for chess tools        |
| `src/assignment/eval/`             | Existing task-evaluation utilities                |
| `packages/agent-sandbox-runtime/`  | Reusable Docker sandbox package                   |
| `tasks/`                           | Task definitions, skills, and experiment fixtures |
| `scripts/`                         | Setup, execution, and evaluation helpers          |
| `tests/`                           | Regression and integration tests                  |

The `chess_app/` checkout is retrieved separately at a pinned source revision. It is not intended to be permanently duplicated inside the main repository.

## 6. Setup with GitHub Codespaces

### Prerequisites

- GitHub account with access to Codespaces.
- OpenAI (or another compatible model) API key, saved as Codespaces Secrets.
- Permission to use Docker inside the development environment.

A Modal account is not required.

### Step 1 — Start Codespaces

Open this repository on GitHub and choose:

**Code → Codespaces → Create codespace on main**

The devcontainer includes Python and Docker-in-Docker support.

Its post-create setup installs dependencies, retrieves the pinned chess application source, and prepares the environment.

### Step 2 — Configure your model API

Keys live **only in Codespaces secrets** (GitHub → Settings → Codespaces → Secrets), each one authorised for this repository:

```
OPENAI_API_KEY      # OpenAI (gpt-5-mini)
DEEPSEEK_API_KEY    # DeepSeek (deepseek-flash = DeepSeek-V4.1-Flash)
```

A Codespace only loads secrets when it starts, so restart it after adding one. We don't use a `.env` file. The code would still read one, but a leftover `.env` quietly chose the model and endpoint for every run, so we removed it. Instead, each run names its endpoint and model explicitly. Settings already in the environment take priority over `.env`.

For DeepSeek, define this helper once per terminal (shell functions don't survive a restart):

```bash
ds() { OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY="$DEEPSEEK_API_KEY" OPENAI_MODEL=deepseek-flash "$@"; }
ds uv run assignment-doctor     # expect: endpoint api.deepseek.com, "Model API accepted the credential"
```

For OpenAI, use the default endpoint: `OPENAI_MODEL=gpt-5-mini make …`.

Check current provider pricing before long runs, especially chess games (see §10). Never commit keys, a `.env` file or unreviewed raw logs.

### Step 3 — Verify the environment

From the repository root:

```
make setup
make sandbox-doctor
make doctor
make test
make test-docker
```

These commands respectively prepare the workspace, check the sandbox runtime, check assignment prerequisites, run non-Docker unit tests, and run Docker integration tests.

`make test` is designed to run without model API calls. Docker integration tests require an available daemon and may build or pull images.

### Step 4 — Try the sandbox directly

```
make sandbox-smoke
```

This is a useful first experiment because it verifies sandbox execution independently of the coding or chess agent.

## 7. How an agent interacts with the sandbox

The `Environment` class provides the interface between the assignment agents and the Docker runtime.

A simplified example:

```
from assignment.env import Environment

with Environment(
    image="python:3.12-slim",
    cwd="/",
) as environment:
    result = environment.execute(
        "python -c 'print(2 + 2)'"
    )

    print(result["returncode"])
    print(result["stdout"])
```

The expected command result is a zero return code and output containing `4` ("python -c 'print(2 + 2)'")

The execution process is:

1. Python creates an `Environment` object.
2. The adapter creates a `Sandbox`.
3. The runtime starts a Docker container using the requested image.
4. The `execute` method sends the command into that container.
5. Docker executes the command and returns process results.
6. The agent receives a structured observation.
7. Exiting the context manager stops the sandbox.

The agent can use the observation when constructing the next model prompt.

This is the foundation of the ReAct loop:

```
Task
  |
  v
Model proposes action
  |
  v
Agent parses tool call
  |
  v
Environment.execute(...)
  |
  v
Docker executes command
  |
  v
Tool observation
  |
  v
Model decides next action
```

The model does not directly control the Docker daemon. It proposes actions through the tool interface implemented by the harness.

## 8. Running the coding agent

The coding agent receives a software issue and uses terminal tools to investigate, modify, and test the application.

Run:

```
make run-code-agent
```

A successful run is designed to produce:

```
artifacts/fix.patch
artifacts/part1-trajectory.json
```

The first artifact contains the proposed source-code patch. The second records the interaction history.

Validate the generated patch:

```
make check-part1
```

The evaluator applies the patch to a fresh testbed and runs relevant tests.

This distinction is important: **the agent proposing a fix is not the same as independently verifying that the fix works.**

Model-driven runs consume API tokens. For small exploratory runs, override `STEPS` to limit the number of model interaction steps.

**Our result (Nov 8, `ds make run-code-agent`):** resolved in 13 steps, FAIL_TO_PASS 1/1 and PASS_TO_PASS 9/9.

- **Workflow:** explore → reproduce the HTTP 500 → fix → test edge cases (stalemate, moves after the game ended, reset) → run the full suite → `invoke_skill` → `patch.txt`.
- **The fix:** play the engine reply only when `self._board.outcome(claim_draw=True) is None`. That's the same check the app already uses for `game_over`, so the two can't disagree.
- **Repeatability:** three repeat trials made the same fix (3/3) using ~111k input and 5.5k output tokens each ([comparison](docs/Coding-Agent-Comparison.md)).


## 9. Context compaction and SWE-bench

A long-running agent accumulates previous prompts, actions, and observations.

Without compaction, its active context can become unnecessarily large and expensive.

Our implementation uses model-generated working memory to summarize older parts of the interaction history while preserving newer actions and important observations.

The repository supports SWE-bench task execution and patch verification.

Example:

```
make run-swebench-agent \
  INSTANCE=django__django-15368

make check-swebench \
  INSTANCE=django__django-15368
```

To study compaction, compare runs with different context thresholds while preserving separate artifacts.

For example:

```
make run-swebench-agent \
  INSTANCE=django__django-15368 \
  COMPACT_THRESHOLD=6000
```

A baseline can be run with `COMPACT_THRESHOLD=0`.

The important evaluation questions are not limited to whether the agent succeeds. We also want to examine how much context it consumes, which information it preserves, and whether compaction changes behavior.

The repository includes token-usage reporting tools:

```
make report-tokens
```

**Our result (Nov 9):** both runs resolved (1/1 + 29/29) with the same fix, `isinstance(attr, Expression)` → `hasattr(attr, 'resolve_expression')` in `bulk_update()`.

| | Compacted (6,000) | Full context |
| --- | ---: | ---: |
| Steps / compactions | 20 / 2 | 19 / 0 |
| Peak prompt | 5,976 | 11,400 |
| Total tokens (incl. 10,205 for summaries) | 105,803 | 140,483 |
| Uncached prompt tokens | 17,748 | 6,870 |

The prompt follows a saw-tooth instead of a ramp, and the working-memory summary kept everything the agent needed. But each compaction rewrites the start of the prompt, which breaks the provider's prompt cache. So compaction cuts input cost only if cached tokens cost more than ~23% of normal input. **Compaction is mainly a capacity tool, not a cost tool.** The full analysis is in [`docs/reports/token-usage-analysis.md`](docs/reports/token-usage-analysis.md).

## 10. Running the chess agent

The chess agent uses the repaired chess application as its environment.

First, produce or supply the validated patch from Part 1. Then run:

```
make run-chess-agent
```

The runner applies the patch, starts the chess application inside Docker, and allows `ChessAgent` to interact with the server.

The expected outputs include:

```
artifacts/part3-trajectory.json
artifacts/game-result.json
```

The trajectory records the agent interaction history. The result file records the final observed game state. It is written even when a run stops early, with a `run_stopped_early` field.

**Settings that matter for long games (learned the hard way):**

| Setting | Default | Why |
| --- | --- | --- |
| `CHESS_TIMEOUT` | `7200` | The sandbox's lifetime. The original 1800 s expired mid-game in our first attempt |
| `CHESS_COMPACT=<tokens>` | `0` (off) | Turns on compaction for chess runs |
| `AGENT_STRIP_REASONING=1` | off | Stops re-sending each move's reasoning. Without it, prompts grew ~10k tokens per move, to 313k |
| `--max-unreachable-steps` | `3` | Circuit breaker: stop when the chess server is gone instead of retrying |

**What happened when we ran it:**

- **Attempt 1:** 55 of 56 moves were accepted and White reached a winning K+Q vs K+B. Then the 30-minute sandbox expired, and the model kept calling `play_move` into a closed port for 138 steps, using 56M input tokens. That led to the circuit breaker: an illegal move is the model's mistake and goes back to it, but a server that's gone is an environment failure.
- **Attempt 2:** with the reasoning stripped it was still ~1 minute per step, because DeepSeek's *thinking per move* dominates. We stopped it by choice. Both partial games are kept locally in `artifacts/attempts/`.

The agent uses tools such as `play_move` and `simulate_move`, with optional programmatic Python execution.

### Why programmatic tools matter

Direct tool calling lets the model request actions individually.

Programmatic tools let the model write a short Python program that performs several operations, including inspecting simulated positions and choosing a move.

This gives the agent a richer action interface.

For example, rather than requesting a sequence of simulated moves manually, the model can write Python that evaluates several candidate moves using the tools provided inside the sandbox.

The repository includes a chess skill workflow:

```
make run-python-skill-agent
```

**Our result (6 steps):** `invoke_skill(select-move)` → `run_python` snippets that search two plies with `simulate_move` and commit one `play_move` each. The first move skipped the search, because the skill's opening rule says to play `e2e4` directly. With a material-only evaluation most moves tie, and ties go to the alphabetically first UCI move, so the bishop drifted `f1b5` → `b5a4` → `a4b3`. **A search is only as good as its evaluation.** This run also exposed a bug: `invoke_skill` was registered twice (HTTP 400 "Tool names must be unique"), now fixed.

### Observation experiments

The assignment also investigates whether providing legal moves in the tool observation affects agent behavior.

The repository contains separate runners for observations with and without legal moves.

A model-specific experiment can be run by overriding the model selection:

```
make run-obs-experiment-legal-moves \
  MODEL=gpt-5-mini \
  MODEL_TAG=gpt5mini
```

Use distinct artifact names and compare equivalent model configurations to avoid overwriting experimental evidence.

Relevant metrics include legal-move errors, tool-call counts, completion status, and token usage.

**Our result (4 runs × 15 steps; gpt-5-mini runs in the `gpt-oss` slot):**

```bash
ds make run-obs-deepseek-no-legal STEPS=15 DEEPSEEK_MODEL=deepseek-flash
ds make run-obs-deepseek-legal    STEPS=15 DEEPSEEK_MODEL=deepseek-flash
OPENAI_MODEL=gpt-5-mini make run-obs-gpt-oss-no-legal STEPS=15 GPT_OSS_MODEL=gpt-5-mini
OPENAI_MODEL=gpt-5-mini make run-obs-gpt-oss-legal    STEPS=15 GPT_OSS_MODEL=gpt-5-mini
make report-obs
```

| Model | Board only | + legal moves |
| --- | --- | --- |
| gpt-5-mini | 3/15 illegal (20%), 7 s/step | 0/15, 4 s/step |
| DeepSeek | 0/15, 12 s/step | 0/15, **43 s/step (6× more thinking)** |

gpt-5-mini's three errors were a notation slip (`c2cxd3`), forgetting it had castled (`e1e2`), and a bishop moved sideways (`c4d4`). None came while it was in check. Listing legal moves fixed validity for the weaker model but changed how the stronger one spent its thinking. See [`docs/reports/observation-experiment.md`](docs/reports/observation-experiment.md). Fifteen steps show a direction, not reliable rates.


## 11. Extending the project with OpenCode

The original assignment focuses primarily on building an agent harness.

Our adaptation adds a second coding-agent workflow: **using OpenCode to improve the harness itself.**

There are two different kinds of agents involved:

| Agent        | Main responsibility                                 |
| ------------ | --------------------------------------------------- |
| CodeAgent  | Solve an assigned software issue                    |
| ChessAgent | Play chess through programmatic tools               |
| OpenCode     | Modify and improve the agent harness implementation |

OpenCode is not the execution sandbox and does not replace our assignment's agent classes.

Instead, we run OpenCode as a coding assistant within a controlled development experiment.

### OpenCode sandbox architecture

```
Harness-improvement task
        |
        v
Pinned baseline source
        |
        v
Docker experiment container
        |
        v
OpenCode coding session
        |
        v
Generated patch
        |
        v
Independent regression tests
        |
        v
Evaluation feedback
        |
        v
Accepted or rejected change
```

The trajectory-logging experiment's Dockerfile installs OpenCode inside the task image during image construction.

OpenCode can then inspect the testbed and propose source changes. The proposed patch is evaluated separately before being accepted into the project.

This setup provides two benefits:

1. **Reproducibility:** We can run experiments against a known baseline.
2. **Controlled integration:** Generated changes do not automatically become accepted project changes.

### OpenCode installation

The trajectory-logging experiment uses:

```
tasks/chess-trajectory-logging/Dockerfile
```

That image installs a pinned OpenCode CLI version and the dependencies needed for the harness task.

The task source, requirements, and evaluation records are kept alongside one another.

OpenCode's free-labeled model catalog was accessible during exploration, but live requests to `opencode/mimo-v2.6-flash-free` (Nov 1) and `opencode/deepseek-v4.1-flash-free` (Nov 9) both failed with **“Free usage limit reached.”** Being listed in the catalog doesn't mean a model will serve requests. The older trajectory-logging repair experiment succeeded under its recorded conditions; later context-window attempts did not produce a patch. The separate Codex integration work is on `feature/codex-sandbox`, not on `main`.

### Free-only mode: OpenCode never uses a paid API

`scripts/run_opencode.py` is **free-only by default**:

- Only `opencode/<id>-free` models are allowed.
- **No** credential is forwarded into the sandbox. Before this change, `OPENAI_API_KEY` was forwarded for every model except one, which we found and fixed.
- The runner refuses to start if anything key-like is visible inside the container.
- OpenCode's error logs are printed, so a quota refusal shows up as `quota_limited` instead of a silent timeout.
- A paid model needs an explicit `--allow-paid-model`.

Check that a free model actually answers before planning around it: `make opencode-probe`. Details are in [`docs/OPENCODE_BACKEND.md`](docs/OPENCODE_BACKEND.md).

### CodeAgent vs OpenCode comparison

We compared our CodeAgent (DeepSeek API) with OpenCode on its free DeepSeek model, on the same Part 1 task, the same grader and the same model family. The aim was to separate the effect of the *harness* from the model (`scripts/compare_coding_agents.py`, `make compare-*`).

- **CodeAgent:** 3/3 resolved.
- **OpenCode:** its free tier refused every request, so there were no trials. No credentials reached the sandbox, and nothing fell back to a paid model.

The harness question is still unanswered, but the runner is ready if the free tier becomes available again. See [`docs/Coding-Agent-Comparison.md`](docs/Coding-Agent-Comparison.md).

## 12. Our trajectory-driven harness improvement experiment

One of our most important experiments took place on October 23rd, 24th, 2026.

### Problem

A chess-agent trajectory exposed a logging deficiency: some final tool observations were missing from the saved interaction history when the agent terminated under certain conditions.

This mattered because incomplete trajectories make it harder to understand the agent's behavior and reliably evaluate its failures.

We turned the observation into a coding task for OpenCode.

### Attempt 1

OpenCode generated a patch that partially addressed the problem.

However, its implementation did not preserve all fields of the original tool messages.

In particular, it omitted the original `role` field.

The candidate passed some tests but failed the full targeted evaluation.

### Attempt 2

We incorporated the evaluation feedback into the task description and reran OpenCode against the pinned baseline.

The second candidate used a different approach, preserving complete original tool messages rather than reconstructing only selected fields.

The implementation was tested before being integrated.

### Recorded evaluation results

| Metric                | Attempt 1 | Attempt 2 |
| --------------------- | --------- | --------- |
| FAIL_TO_PASS          | 1/2       | 2/2       |
| PASS_TO_PASS          | 1/1       | 1/1       |
| Targeted public tests | 2/3       | 3/3       |

Additional recorded validation for Attempt 2:

- Broader isolated regression tests: **15/15 passed**
- Repository non-Docker tests: **38/38 passed**
- Docker integration tests: **3/3 passed**
- Combined repository tests: **41/41 passed**

These results are recorded in:

```
tasks/chess-trajectory-logging/
    experiment-records/
        SESSION_NOTES.md
```

The experiment also retains generated patch and evaluation evidence.

### What we learned

The key lesson was not simply that OpenCode generated a useful patch.

It was that **specific evaluation feedback led to a more complete implementation that passed the targeted and broader regression tests**.

The workflow became:

```
Agent trajectory
      |
      v
Identify failure
      |
      v
Define improvement task
      |
      v
OpenCode generates patch
      |
      v
Run tests
      |
      v
Analyze failures
      |
      v
Improve task instructions
      |
      v
OpenCode generates revised patch
      |
      v
Evaluate again
      |
      v
Review and integrate
```

This was our first concrete experiment in evaluation-driven harness improvement.

### Limitations of the experiment

The recorded tests establish that the accepted implementation passed those test suites at that milestone.

They do not establish that the chess agent's gameplay became stronger.

The session notes also identify remaining work, including replaying a live model-driven chess trajectory against the revised logger and testing additional malformed-history and logging-failure cases.

---

## 13. Why we did not adopt Harness²

We investigated Google's **Harness²** ideas because they align with our goal: use real agent trajectories and evaluation feedback to improve the software surrounding an LLM, rather than treating model prompting as the only lever.

**We decided not to use Harness² itself.** We went through the Harness² GitHub repo and tried to set it up. Real runs needed a **Google Cloud account (Vertex AI)** and **Tencent's WorkBuddy** benchmark/evaluation setup. Both go against the plan behind this whole adaptation: keep everything under our own control. We removed one external dependency (Modal), and Harness² would have added two more.

Reading the repo also showed that its idea of a harness (system prompt, tools, memory, skills, the orchestration loop) is the same thing Assignment 1 builds by hand. Harness² automates *editing* that harness through Propose → Probe → Compose. The assignment neither asks for nor grades that optimiser.

Instead, we kept the feedback-driven *method*, with a simpler, inspectable loop:

1. Run CodeAgent or ChessAgent with a recorded configuration.
2. Preserve the trajectory, tool observations, result, and token usage.
3. Diagnose a specific, reproducible harness failure.
4. Give a narrowly scoped coding task to OpenCode (or, on a separate branch, Codex).
5. Inspect the proposed patch; run independent regression tests.
6. Accept or reject the patch, then compare controlled agent runs if claiming behavioral improvement.

The [trajectory-logging experiment](tasks/chess-trajectory-logging/experiment-records/SESSION_NOTES.md) demonstrates a **manual feedback-and-repair loop**: a first patch failed targeted checks; a revised patch passed them. This does *not* establish a fully automatic self-improving system, a general-purpose judge, or improved chess-playing strength.

**Scope decision:** Harness² integration is dropped. A future evaluation-driven project may reuse the underlying lessons, but no Harness² deployment is required to finish Assignment 1.

## 14. Testing and reproducibility

The project provides several levels of verification.

| Command                  | Purpose                                  |
| ------------------------ | ---------------------------------------- |
| `make sandbox-doctor`    | Inspect sandbox runtime prerequisites    |
| `make sandbox-smoke`     | Verify basic sandbox execution           |
| `make doctor`            | Check assignment setup                   |
| `make test`              | Run non-Docker unit tests                |
| `make test-docker`       | Run Docker integration tests             |
| `make test-chess-docker` | Run chess sandbox integration tests      |
| `make check-part1`       | Validate a generated chess-app patch     |
| `make check-swebench`    | Evaluate a SWE-bench patch               |
| `make report-tokens`     | Analyze recorded token usage             |
| `make report-obs`        | Analyze recorded observation experiments |
| `make opencode-probe`    | Check that the OpenCode free model answers (no API key) |
| `make compare-report`    | Summarise CodeAgent vs OpenCode trials   |

GitHub Actions is also used to test repository changes.

Passing tests is evidence about the cases covered by those tests, not proof that an agent will succeed on every task or that the system meets every original course grading requirement.

### Reproducibility principles

The project emphasizes:

- Pinned task-source revisions.
- Isolated Docker testbeds.
- Saved agent trajectories.
- Separate generated patches and evaluation outputs.
- Regression tests for previously observed failures.
- Explicit experiment records.
- Human review before integrating generated changes.

These principles will also support future evaluation-harness experiments.

## 15. Current state: completed work, adaptations, and open gaps

This section is the source of truth for **what is on `main`**, rather than an aspirational research roadmap. Evidence below comes from committed code, tracked experiment records, and CI. Files in ignored directories such as `artifacts/` may exist in a Codespace but cannot be certified by viewing GitHub alone.

### 15.1 Completed on `main`

- **Assignment 1 agent foundations:** Shared ReAct loop, tool-call dispatch and observations, CodeAgent, skills, model-generated context compaction, and ChessAgent with `play_move`, `simulate_move`, `run_python`, and chess skill handling.
- **Self-hosted sandbox adaptation:** Reusable Docker runtime package, `Environment` compatibility adapter, pinned chess application setup, and Codespaces Docker-in-Docker development workflow.
- **Test and task runners:** Repository unit tests, Docker integration tests, coding-task patch evaluator, SWE-bench runner and validator, chess runners, and observation-experiment commands.
- **Evaluation extension:** `scripts/eval_chess_trajectory.py`, `scripts/run_chess_experiment.py`, `scripts/aggregate_chess_trials.py`, `scripts/compare_chess_evaluations.py`, plus test coverage for these tools. The recorded [`baseline-003.json`](experiments/eval-harness/baseline-003.json) has three 3-step `gpt-5-mini` trials (9/9 moves accepted, no game finished).
- **OpenCode repair experiment:** The recorded second trajectory-logging patch passed 2/2 fail-to-pass checks, 1/1 pass-to-pass check, and 3/3 targeted public tests. That's a **logging fix**, not better chess play.
- **Harness fixes found by running the agents (Nov 8–9):**
  - free-only OpenCode mode, closing an API-key leak path (PR #2);
  - OpenCode quota errors made visible (PR #3);
  - a chess circuit breaker, plus `game-result.json` written on early stops (PR #6);
  - a duplicate `invoke_skill` tool (PR #7).

**Tests:** 138 passed / 3 deselected (non-Docker) and 3/3 Docker integration tests on `main`, Nov 9, 2026.

### 15.2 What is adapted, rather than original

- **Execution:** **Modal → Docker**, in GitHub Codespaces.
- **Models:** `deepseek-flash` (DeepSeek-V4.1-Flash, `api.deepseek.com`) instead of the course's DeepSeek-V4-Flash `0731` endpoint, which isn't available to us. gpt-5-mini replaced GPT-OSS-120b in the observation experiment; the files keep the official `gpt-oss` names.
- **Run settings:** the chess runs used `AGENT_STRIP_REASONING=1` and a 2-hour sandbox. The A/B and skill runs were cut to 15 and 6 steps.
- **Extensions:** the trajectory evaluation, the OpenCode workflow and the coding-agent comparison are independent research extensions.
- **Not merged:** the Codex CLI feature is on `feature/codex-sandbox`, not in `main`.
- **Not used:** Harness², for the reasons in [Section 13](#13-why-we-did-not-adopt-harness). Our manual diagnosis → patch → independent test loop is inspired by feedback-driven harness improvement, but it isn't Harness².

### 15.3 Status against the original Assignment 1

| Requirement | Status | Evidence |
| --- | --- | --- |
| **Part 1: coding repair** | ✅ | `fix.patch` + `part1-trajectory.json`; `make check-part1` RESOLVED (1/1, 9/9) |
| **Part 2: SWE-bench compaction** | ✅ | Compacted patch + trajectory resolved with 2 compaction events; a full-context control also resolved; [token report](docs/reports/token-usage-analysis.md) |
| **Part 3: basic chess run to a terminal state** | ⏭️ skipped | Two partial games (see §10). Skipping it costs the one `game_over: true` row |
| **Part 3: observation A/B** | ✅ (15-step runs) | 4 trajectories + results; [observation report](docs/reports/observation-experiment.md) |
| **Part 3: programmatic chess skill** | ✅ (6-step run) | `part3-python-skill-trajectory.json`: `invoke_skill` → `run_python` + `simulate_move` → `play_move` |
| **Final submission** | not needed | We aren't submitting. `AI_USAGE.md` and `make package` remain optional |

The run artifacts are in the Git-ignored `artifacts/` folder of the Codespace and its downloaded backups, not in this repository. To use the final reports as artifacts: `cp docs/reports/*.md artifacts/`.

### 15.4 Research work intentionally not on the completion path

Unified coding/chess evaluation, an LLM trajectory judge, automatic self-improvement, additional provider experiments, and chess-specific context optimization remain **out of scope for completing Assignment 1**. The separate `feature/codex-sandbox` work should be reviewed on its own merits before any merge. We are not pursuing `experiment/chess-context-v2`.

## 16. Lessons learned

This project began as an exercise in building an agent. It has evolved into a study of the infrastructure and feedback systems that make agents useful.

Our major lessons so far are:

- **1. An agent is not just a model.** The harness determines how the model observes, acts, recovers from errors, and interacts with its environment.
- **2. Execution infrastructure should be replaceable.** By separating `Environment` from the sandbox backend, we can change execution infrastructure without rewriting the agent's core logic.
- **3. Sandboxing makes experimentation more controlled.** Disposable Docker containers help separate generated code from the main development environment.
- **4. Trajectories are essential evidence.** Without reliable action and observation logs, diagnosing agent failures becomes difficult.
- **5. Tests improve coding-agent reliability.** A generated patch should be independently evaluated before integration.
- **6. Harness improvement is an empirical process.** A successful experiment needs a reproducible baseline, a proposed change, and comparable evaluation results.
- **7. What stays in the context decides speed and cost.** Re-sending every move's reasoning produced 300k-token prompts. Compaction cut tokens but broke the prompt cache. Measure both.
- **8. Tell model mistakes apart from environment failures.** Recoverable errors are right for an illegal move and wrong for a dead server. A harness needs a circuit breaker.
- **9. Observation design changes how a model spends its thinking.** Listing legal moves fixed the weaker model's errors and made the stronger one deliberate 6× longer.
- **10. A free tier isn't a guarantee.** Probe before planning around free inference, and never let a quota failure fall back to a paid key.
- **11. Running the system finds bugs that unit tests don't.** Four real harness bugs surfaced only once the agents ran end to end.


## 17. Optional next steps

Assignment 1 is complete for learning purposes. If we come back to it:

1. **Make `reasoning_effort` configurable** (it's hard-coded to `"medium"`) and measure thinking effort against move quality and speed. This targets the bottleneck that made full DeepSeek games take over an hour.
2. **Finish a full game in the fastest condition** (gpt-5-mini with legal moves, ~4 s per step) to tick the terminal-state requirement.
3. **Re-run the A/B at full length**, with several trials per condition, to turn directions into rates.
4. **Retry the OpenCode comparison** if its free tier serves requests again (`make opencode-probe`).
5. **For a full submission:** write `AI_USAGE.md`, copy the reports into `artifacts/`, run `make package` and inspect the ZIP. `scripts/package_submission.py` lists missing files but still builds an incomplete ZIP.

---

**Project philosophy:** Build the agent, observe its behavior, evaluate failures, and improve the harness based on measured evidence.
