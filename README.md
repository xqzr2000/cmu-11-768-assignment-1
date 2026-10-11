# CMU 11-768 Assignment 1 — Docker adaptation

An **independent adaptation** of the CMU 11-768 Assignment 1 starter. The original authors and course instructions remain credited in `ASSIGNMENT.md`. This fork uses the OpenAI API and local Docker task sandboxes instead of Modal. The adaptation is not guaranteed to satisfy the original Modal-specific grading requirements.

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

## Codespaces or local VS Code

1. Open this repository in **GitHub Codespaces** or open its folder in VS Code with Docker Desktop/Engine running and choose **Dev Containers: Reopen in Container**.
2. The devcontainer installs `uv`, runs `make setup` (`uv sync` plus a checkout of the pinned upstream `chess_app` source), and prepares an ignored `.env` if it is absent. No second sandbox Codespace is required.
3. In Codespaces, configure `OPENAI_API_KEY` under Codespaces secrets and grant this repository access; set `OPENAI_MODEL` as a secret or in ignored `.env`. For local VS Code, put both in `.env`. Never commit credentials.
4. Check the setup:

```bash
make sandbox-doctor  # Docker reachable
make sandbox-smoke   # starts a container, executes Python, cleans up
make doctor          # API and chess source checks
make test            # offline harness + sandbox runtime unit tests
make test-docker     # live Docker tests; pulls/builds images and may be slow
```

You can run `make setup` manually if automatic post-create setup is interrupted. In a network-enabled environment, generate and commit the single root `uv.lock` using `uv lock` (then use `uv sync --locked` for reproducibility).

## Run the assignment

```bash
make run-code-agent
make check-part1           # requires artifacts/fix.patch
make run-chess-sandbox
make run-chess-agent
make run-swebench-agent
make check-swebench        # requires a generated SWE-bench patch
make report-tokens
make report-obs
```

All agent model calls can incur OpenAI API usage charges. Codespaces usage may also be billed. No Modal subscription is required. See `Makefile`, `ASSIGNMENT.md`, and `MIGRATION.md` for additional context.

## Operations, security, and limitations

- The bundled runtime provides `uv run agent-sandbox doctor|smoke|list|cleanup`. `cleanup` removes managed Docker containers; use it carefully.
- Sandboxes enforce CPU, memory, process, lifetime and localhost port limitations. They do **not** provide VM-grade isolation; avoid executing intentionally malicious code and do not publicly forward sandbox ports. Secrets are not passed into task containers by default.
- The task's `chess_app/` source is fetched at the exact pinned base commit by `scripts/bootstrap_sources.sh`. It is **not bundled** in this repository, so that task requires one network-enabled setup operation.
- Full SWE-bench compatibility is not established by unit tests. Published images may be large and `linux/amd64` only; ARM Macs may require emulation. Test on your actual Codespace or local environment.
- The original CMU source ZIP did not include a redistribution license. **Review upstream rights before making this fork public.** The MIT license in `packages/agent-sandbox-runtime/LICENSE` applies to the runtime package only, not to CMU assignment material.

## Updating an existing GitHub repository by browser

Read `UPDATE_GITHUB.md` before uploading this ZIP; it explains hidden files, why the ZIP's containing folder must not be uploaded as a nested directory, and why the GitHub web uploader may leave obsolete files behind rather than deleting them.
