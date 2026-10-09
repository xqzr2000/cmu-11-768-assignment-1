# cmu-11-768-assignment-1 — Docker Adaptation

This is an **independent adaptation** of the CMU 11-768 Assignment 1 starter (original attribution and instructions are preserved in `ASSIGNMENT.md`). It uses OpenAI via the OpenAI SDK and the standalone `russells-agent-sandbox` repo rather than the original course Modal service. This adaptation is not guaranteed to meet Modal-specific assignment grading rules.

## Repository architecture

| Public repo | Purpose |
| --- | --- |
| `cmu-11-768-assignment-1` (this one) | Agent code, OpenAI integration, chess / SWE-bench task definitions, evaluation |
| `russells-agent-sandbox` | Disposable Docker images and containers, execution interface, private localhost ports |

The Python dependency retains the name **`agent-sandbox-runtime`**, despite the GitHub repository being called **`russells-agent-sandbox`**.

The harness expects **a sibling checkout** called `../russells-agent-sandbox`. A one-time `make setup` fetches this from the same GitHub owner as `cmu-11-768-assignment-1`, or you can set `SANDBOX_RUNTIME_GIT_URL`. The runtime is linked through an editable local `uv` path dependency for development. The bootstrap script defaults to the runtime tag `v0.1.0`, which you must create after publishing the sandbox repository.

## Open in Codespaces or local VS Code

1. **Publish the sandbox repository first**, named `russells-agent-sandbox` under your GitHub user/org, and tag the initial release `v0.1.0`.
2. Publish this repo as `cmu-11-768-assignment-1` under the same owner. In GitHub select **Code → Codespaces → Create codespace**. Or open it in VS Code and select **Dev Containers: Reopen in Container** (requires Docker Desktop/Engine and Dev Containers extension).
3. The devcontainer provisions a dedicated Docker-in-Docker engine and executes `make setup`. It clones the sibling sandbox runtime if necessary, syncs Python dependencies with `uv`, and checks out the public chess-app at its exact base commit. Run `make setup` manually if automatic setup is interrupted.
4. Set `OPENAI_API_KEY` as a **GitHub Codespaces secret** (already done for your account), and optionally `OPENAI_MODEL`. For local VS Code, put them in ignored `.env` created from `.env.example`. The default API base is `https://api.openai.com/v1` and the example model is `gpt-5-mini`.
5. Verify with the commands below.

```bash
make sandbox-doctor  # Docker daemon connectivity
make doctor          # Docker + source revision + OpenAI API configuration
make test            # offline unit tests
make test-docker     # real container and chess server integration (may pull/build images)
```

Try a single sandbox without an OpenAI key:

```bash
make sandbox-smoke
```

## Run the assignments

```bash
make run-code-agent
make check-part1
make run-chess-sandbox
make run-chess-agent
make run-swebench-agent
make check-swebench
make report-tokens
make report-obs
```

Additional experiment targets are listed in `Makefile`. Experiment calls to the OpenAI API may be billed; Docker local execution does not require Modal credit but consumes machine and Codespaces resources. `make check-part1` and `make check-swebench` require an agent-generated patch first.

## Runtime and compatibility

The sandbox backend starts local, throwaway Docker task containers with a bounded lifetime, CPU/memory/process caps, no host bind mounts, and ports bound only to localhost. Its Docker engine is separate from the development editor process in the default devcontainer. It is **not** equivalent to a hardened virtual machine. Avoid executing actively malicious code and keep Codespaces ports private.

SWE-bench published images may be x86_64-only, and image pulls can be large. On Apple Silicon, Docker Desktop may need amd64 emulation. Successful local Docker operation does not itself prove SWE-bench evaluation compatibility; run `make test-docker` and the appropriate evaluation for full verification.

Before publishing publicly, **review redistribution permissions for the original CMU course content**. The original archive did not include a license, and this fork does not assert redistribution rights. Add a LICENSE only for material you are authorized to license; preserve upstream notices.

### Repository setup notes

- `uv.lock` must be regenerated (`uv lock`) after the runtime migration on a network-connected development machine; the original Modal-based lock was removed because it did not match this dependency graph. Commit both repos' generated lockfiles before using `uv sync --locked` in CI.
- Each checkout is independent, but the harness must be checked out beside the runtime at the expected path. The path in `pyproject.toml` is tied to the checkout directory `../russells-agent-sandbox`; keep this checkout name or update the path and CI/bootstrap script together.
- Source clone `chess_app/` is gitignored and downloaded by `scripts/bootstrap_sources.sh`; it is **not republished** as part of this repo.
- A failed run may leave a container only until its bounded lifetime expires; use `uv run agent-sandbox list` or `uv run agent-sandbox cleanup` to inspect/remove the runtime's containers.

## Origins

Original assignment scaffold authors: Weiwei Sun and Saujas Vaduguru; course staff and additional attribution are preserved in `ASSIGNMENT.md`. The original course describes a Modal-based workflow; in this fork use `README.md` and `Makefile` for operational setup.
