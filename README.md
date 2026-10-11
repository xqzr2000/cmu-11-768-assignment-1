# CMU 11-768 Assignment 1 — Docker adaptation

An **independent adaptation** of the CMU 11-768 Assignment 1 starter. The original authors and course instructions remain credited in `ASSIGNMENT.md`. 

This fork uses the OpenAI API and local Docker task sandboxes instead of Modal. 


## One repository, two Python packages

| Path | Role |
| --- | --- |
| `src/assignment/` | Agent, task, chess application integration, evaluation, `Environment` adapter |
| `packages/agent-sandbox-runtime/` | Reusable Docker image builder and sandbox execution backend |
| `.devcontainer/` | A **single** Codespaces / VS Code development environment with Docker-in-Docker |
| `tasks/` | Chess and SWE-bench task descriptions and patches |
| `tests/` | Harness tests; runtime tests also live under `packages/agent-sandbox-runtime/tests/` |

The project is a single **uv workspace**. The root `pyproject.toml` resolves `agent-sandbox-runtime` directly from `packages/agent-sandbox-runtime`, with no external repository, release tag, GitHub authentication, or sibling folder dependency. A single `uv sync` installs both Python packages.

**Execution:** Agent → `assignment.env.Environment` → `agent_sandbox_runtime.Sandbox` → local Docker engine → a disposable Docker task container. The sandbox Python *package* is not a separate server; the **actual command executes in Docker**, outside the agent's development Python environment. The OpenAI model endpoint handles inference only.


Read `UPDATE_GITHUB.md` before uploading this ZIP; it explains hidden files, why the ZIP's containing folder must not be uploaded as a nested directory, and why the GitHub web uploader may leave obsolete files behind rather than deleting them.
