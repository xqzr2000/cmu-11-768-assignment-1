# Russell's Take on CMU 11-768 Assignment 1

> Building an AI agent harness with Docker, the OpenAI API, and OpenCode's free models to understand and improve agent systems. I am a student at Pitt and am not registered at CMU for any academic credit.

A hands-on adaptation of [CMU 11-768 Assignment 1: Build an Agent Harness](https://github.com/cmu-agents/assignment-1), developed to study how AI agents interact with tools, execute code safely, maintain context, and improve their performance through evaluation feedback.

This project replaces the original assignment's Modal execution infrastructure with a reusable Docker sandbox running inside GitHub Codespaces. It also extends the assignment with OpenCode-driven harness improvement experiments and trajectory- and telemetry-based analysis.


## Current snapshot (November 5, 2026)

**Status:** The core Assignment 1 agent harness is implemented on `main` and the local Docker-based adaptation is working. A deterministic chess evaluation runner, multi-trial aggregation, and a recorded three-trial baseline are also on `main`. **The original Assignment 1 is not yet verified complete as a set of required runs and submission artifacts.**

| Area | Current evidence | Boundary |
| --- | --- | --- |
| ReAct harness, CodeAgent, context compaction, ChessAgent, skills, and tools | Implemented and covered by repository tests | Private assignment grading is not verified |
| Modal replacement | `Environment` adapter + disposable Docker task containers in GitHub Codespaces | Not a production-hardened sandbox |
| Evaluation extension | Offline chess evaluator, batch runner, trial aggregator, baseline summaries | The three-step baseline does not measure full-game skill |
| OpenCode harness repair | Recorded second attempt passes 2/2 fail-to-pass and 1/1 pass-to-pass checks | A logging repair is not proof of improved gameplay |
| Codex CLI integration | Developed separately on `feature/codex-sandbox` | **Not part of `main`** |
| Assignment 1 deliverables | Source and runner commands exist | Final patch/trajectory/report collection has not been verified from this Git checkout |

At commit `eb01f0a`, the recorded verification is **105 passing non-Docker tests and 3 passing Docker integration tests**. The [November 2, 2026 GitHub Actions run](https://github.com/xqzr2000/cmu-11-768-assignment-1/actions/runs/41377559231) passed both the unit and Docker jobs. This describes the state verified at that commit; it is not a guarantee about every subsequent commit.

For the actionable completion checklist, see [Section 15](#15-current-state-completed-work-adaptations-and-open-gaps) and [Section 17](#17-prioritized-next-steps). The [evaluation progress record](experiments/eval-harness/PROGRESS.md) is retained as experiment history, but its old branch handoff is not the current `main` roadmap.

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
| Model inference     | OpenAI-compatible API                    | Generate agent actions and reasoning                     |
| Sandbox runtime     | Docker                                   | Execute untrusted task commands in disposable containers |
| Coding agent        | `CodeAgent`                              | Repair software and solve coding tasks                   |
| Chess agent         | `ChessAgent`                             | Play chess using tools and programmatic actions          |
| Coding assistant    | OpenCode                                 | Experiment with harness code improvements                |
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
| Course-provided/default OpenAI-compatible model endpoint | Configurable OpenAI-compatible client; recorded baseline uses `gpt-5-mini` | Run independent experiments using our own model API account |
| Course-oriented source/testing flow | `uv` workspace, pinned chess source bootstrap, Docker and GitHub Actions tests | Reproduce the environment and catch regressions without a Modal account |
| ReAct loop, CodeAgent, compaction and ChessAgent | Original agent abstractions preserved, with Docker-specific adapters | Keep the focus on agent behavior rather than replacing the whole harness |
| No general repeated-trial chess evaluation in the assignment workflow | Offline trajectory scorer, experiment runner, trial aggregation, committed summaries | Measure observed behavior and provide reproducible evidence |
| No external harness-development coding agent required | Optional OpenCode-based repair experiment | Test whether feedback can improve the harness itself |

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

Create a Codespaces secret:

```
OPENAI_API_KEY
```

For a Codespaces secret, authorize access to this repository.

The project also supports configuration through an ignored `.env` file, if you want to set it up locally.

Example:

```
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5-mini
OPENAI_MAX_RETRIES=5
```

Use a model your API account supports, and check current provider pricing before running experiments.

Never commit `.env`, API keys, private tokens, or unreviewed raw logs containing sensitive information.

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

The trajectory records the agent interaction history. The result file records the final observed game state.

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

OpenCode's free-labeled model catalog was accessible during exploration, but a live `opencode/mimo-v2.6-flash-free` request failed with **“Free usage limit reached.”** Model listing is not evidence of inference access. The older trajectory-logging repair experiment succeeded under its recorded conditions; later context-window attempts did not produce a patch. The separate Codex integration work is on `feature/codex-sandbox`, not on `main`.

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

**We decided not to implement Harness² itself.** The external research workflow we explored involved Google Cloud infrastructure and a WorkBuddy-related evaluation arrangement. Reproducing that setup would have added infrastructure and evaluation-provider dependencies to a project whose central adaptation is to run the execution environment ourselves in GitHub Codespaces. Building a faithful autonomous optimization system would also have distracted from completing the core Assignment 1 exercises.

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
- **Evaluation extension:** `scripts/eval_chess_trajectory.py`, `scripts/run_chess_experiment.py`, `scripts/aggregate_chess_trials.py`, `scripts/compare_chess_evaluations.py`, plus test coverage for these tools.
- **Recorded baseline:** [`baseline-003.json`](experiments/eval-harness/baseline-003.json) contains three `gpt-5-mini` trials, 9/9 accepted moves, zero tool errors, and a 3,628-token mean. **All three trials stopped at the three-step limit; zero games finished.**
- **OpenCode repair experiment:** The recorded second trajectory-logging patch passed 2/2 fail-to-pass checks, 1/1 pass-to-pass check, and 3/3 targeted public tests. This is evidence of a **logging implementation fix**, not better chess play.

**Verified test checkpoint:** 105 passed / 3 deselected in the repository non-Docker suite, and 3 passed in the Docker suite. Both jobs of the [November 2 CI run](https://github.com/xqzr2000/cmu-11-768-assignment-1/actions/runs/41377559231) completed successfully.

### 15.2 What is adapted, rather than original

Our **Modal → Docker** change concerns where agent-generated commands execute. Our **model selection** uses a configurable OpenAI-compatible API, with `gpt-5-mini` used for the recorded chess baseline rather than the course's default provider/model. Our **trajectory evaluation and OpenCode workflow** are independent research extensions. These do not replace the official Assignment 1 requirements for actual patches, trajectories, analysis reports, and replayable evidence. The Codex CLI feature is developed separately and is not merged into `main`.

We considered Harness² but **dropped implementing it**, for the infrastructure/dependency and scope reasons in [Section 13](#13-why-we-did-not-adopt-harness). Our manual diagnosis → patch → independent test loop is inspired by feedback-driven harness improvement; it is not Harness².

### 15.3 Still needed to complete the original Assignment 1

The code paths exist, but **a working CLI or passing unit test is not the same as a submitted successful run**. The original [Assignment 1 specification](https://github.com/cmu-agents/assignment-1/blob/main/ASSIGNMENT.md) requires evidence for all three parts.

| Priority | Requirement | What to verify or produce |
| --- | --- | --- |
| P0 | **Part 1: coding repair** | `artifacts/fix.patch`, `artifacts/part1-trajectory.json`, and a successful independent `make check-part1` run |
| P0 | **Part 2: SWE-bench compaction** | Passing `django__django-15368.patch` and trajectory, verified compaction event and reduced active context, a no-compaction control run, and `artifacts/token-usage-analysis.md` |
| P0 | **Part 3: basic chess run** | `artifacts/part3-trajectory.json` and `artifacts/game-result.json` showing a terminal chess state; the existing three-step baseline is not this deliverable |
| P0 | **Part 3: observation A/B** | Four model/observation combinations with distinct trajectories and results (DeepSeek and GPT-OSS; legal moves shown/hidden), plus `artifacts/observation-experiment.md` |
| P0 | **Part 3: programmatic chess skill** | `artifacts/part3-python-skill-trajectory.json` demonstrating `invoke_skill`, then `run_python` using `simulate_move` and `play_move` |
| P1 | **Final submission** | `AI_USAGE.md`, all required artifacts, an independently reviewed ZIP, and no credentials or unrequested files |

**Verification status:** These run artifacts are **not in the tracked `main` tree** because `artifacts/` is Git-ignored. Do not assume they are absent from, or complete in, an existing Codespace. Inventory and validate those local files before paying for any new model inference. The committed Baseline 003 summary does not substitute for the official Part 3 files.

The existing `scripts/package_submission.py` creates a ZIP and prints missing file names rather than failing outright when required artifacts are absent; review its output and the archive contents before declaring a submission complete. Private course tests and original Modal-specific grading behavior have not been established for this independent adaptation.

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


## 17. Prioritized next steps to finish Assignment 1

Do not start a new agent-research branch or repeat model-provider diagnostics until the original Assignment 1 evidence has been audited.

1. **Verify the stable baseline.** Use `main`, run `make setup`, `make test`, and `make test-docker`; record the current commit and results. These tests do not call the model by design.
2. **Inventory ignored local artifacts.** Check `artifacts/` and any saved private experiment outputs against the exact [official submission list](https://github.com/cmu-agents/assignment-1/blob/main/ASSIGNMENT.md#submission). Back up valuable raw trajectories before deleting a Codespace.
3. **Fill only missing end-to-end evidence.** Prioritize a verified Part 1 chess-app fix, a passing compacted SWE-bench patch with a full-context comparison, a terminal chess run, the four observation A/B runs, and a programmatic skill trajectory. Each live run may incur API charges.
4. **Finish the required analysis and package.** Produce the token-usage and observation reports, `AI_USAGE.md`, and the ZIP. Inspect `scripts/package_submission.py` output: it currently reports missing artifacts without refusing to create an incomplete ZIP.
5. **Freeze a reproducible milestone.** Document verified outcomes and remaining limitations, check that no secrets are committed, and only then decide whether independent Codex or evaluation research is worth resuming.

**Success condition:** The adapted Assignment 1 source is tested, each required run artifact and report exists and has been independently checked, and the final ZIP is complete. Our Docker/GPT substitution remains a learning adaptation; it should not be described as course-approved or identical to the original Modal execution path.

---

**Project philosophy:** Build the agent, observe its behavior, evaluate failures, and improve the harness based on measured evidence.
