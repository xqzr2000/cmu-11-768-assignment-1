# Russell's Take on CMU 11-768 Assignment 1

> Building an AI agent harness with Docker, the OpenAI API, and OpenCode's free models to understand and improve agent systems. I am a student at Pitt and am not registered at CMU for any academic credit.

A hands-on adaptation of [CMU 11-768 Assignment 1: Build an Agent Harness](https://github.com/cmu-agents/assignment-1), developed to study how AI agents interact with tools, execute code safely, maintain context, and improve their performance through evaluation feedback.

This project replaces the original assignment's Modal execution infrastructure with a reusable Docker sandbox running inside GitHub Codespaces. It also extends the assignment with OpenCode-driven harness improvement experiments and trajectory- and telemetry-based analysis.


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

As of October 2026, we are using the free inference tiers for MiMo-V2.6-Flash and DeepSeek V4.1 Flash provided by OpenCode. However, because the availability and pricing of free models are subject to change, this no-cost inference should not be considered permanent. We will integrate OpenAI's gpt-5-mini once this free lunch is over.

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

## 13. What we learned from Harness²

We explored Google's Harness² approach, which motivated our interest in recursive, feedback-driven harness improvement.

The general idea is to collect information from agent runs, identify weaknesses in the surrounding harness, modify that harness, and evaluate the new version. A fully automated loop requires additional orchestration, evaluator integration, and reliable mechanisms for proposing and accepting changes.

After trying it, we decided **not** to adopt Harness² itself. Two practical constraints drove this:

- It requires a GCP account.
- Evaluation is done through a partnership with Tencent's WorkBuddy.

Neither fits our goal of keeping everything under our own control.

For our learning project, we therefore chose a simpler approach:

- Collect trajectories and telemetry.
- Diagnose an observable failure.
- Prepare a coding task.
- Let OpenCode generate a candidate patch.
- Evaluate the patch using regression tests.
- Review the results.
- Repeat if necessary.

This retains the essential learning loop without implementing a full autonomous recursive improvement system or depending on external accounts and evaluation services.

**Our project does not claim to implement Google's complete Harness² framework.**

The abandoned Harness² evaluation and the successful manual OpenCode experiment are separate efforts.

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

## 15. Current status — October 2026

### Implemented and tested

- Local Docker sandbox runtime integrated as a workspace package.
- GitHub Codespaces development environment with Docker support.
- OpenAI-compatible inference configuration.
- Assignment agent runners and sandbox execution adapter.
- Chess application integration and programmatic tool support.
- SWE-bench task runner and patch evaluation utilities.
- Context compaction support and reporting tools.
- OpenCode-based harness-improvement experiments.
- Trajectory-logging improvements supported by recorded regression results.

### Explored, with further validation needed

- Chess-agent strategic performance.
- Observation-format effects across model configurations.
- Benefits and tradeoffs of context compaction.
- Generalization of OpenCode improvements beyond individual test cases.
- Manual Harness²-inspired feedback loops.

### Not yet implemented

- A unified evaluation framework across chess and coding agents.
- A systematic labeled trajectory dataset for measuring evaluator accuracy.
- An OpenAI-based trajectory judge integrated into a reusable evaluation runner.
- Automatic baseline-versus-improved harness scorecards.
- A production-ready automated self-improving harness.

---

## 16. Lessons learned

This project began as an exercise in building an agent. It has evolved into a study of the infrastructure and feedback systems that make agents useful.

Our major lessons so far are:

- **1. An agent is not just a model.** The harness determines how the model observes, acts, recovers from errors, and interacts with its environment.
- **2. Execution infrastructure should be replaceable.** By separating `Environment` from the sandbox backend, we can change execution infrastructure without rewriting the agent's core logic.
- **3. Sandboxing makes experimentation more controlled.** Disposable Docker containers help separate generated code from the main development environment.
- **4. Trajectories are essential evidence.** Without reliable action and observation logs, diagnosing agent failures becomes difficult.
- **5. Tests improve coding-agent reliability.** A generated patch should be independently evaluated before integration.
- **6. Harness improvement is an empirical process.** A successful experiment needs a reproducible baseline, a proposed change, and comparable evaluation results.


## 17. Next phase — Evaluation-driven agent improvement

Our next objective is to turn these lessons into a reusable evaluation framework.

Our next research direction is inspired by [CMU Assignment 2](https://github.com/cmu-agents/assignment-2), which focuses on evaluating agent behavior and outputs.

Rather than creating an entirely separate infrastructure stack, we intend to extend the existing repository.

The proposed development branch is:

```
experiment/eval-harness
```

The branch will start from the merged `main` baseline.

### Planned architecture

```
CodeAgent / ChessAgent
          |
          v
     Docker Sandbox
          |
          v
 Trajectory + Telemetry
          |
          v
 Evaluation Framework
    |           |
    v           v
Python       OpenAI
Checks       Judge
    |           |
    +-----+-----+
          |
          v
    Evaluation Report
          |
          v
    OpenCode Improvement
          |
          v
   Regression Evaluation
```

We plan to begin with one real chess trajectory and a small deterministic evaluator.

The initial questions will include:

- Did the agent complete the task?
- Were invalid tool calls made?
- Was the step limit exceeded?
- Did the final result match the objective?

We will then explore LLM-based diagnosis, human-labeled evaluation data, precision, recall, Matthews correlation coefficient, and before-and-after harness comparisons.

The ultimate goal is to make harness improvement measurable rather than relying on subjective impressions.

This work is planned and should not be confused with functionality already present in `main`.


---

**Project philosophy:** Build the agent, observe its behavior, evaluate its failures, improve the harness, and measure the results.
