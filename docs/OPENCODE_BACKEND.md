# Optional OpenCode sandbox backend (experimental)

This branch adds a **second** coding backend; it does not replace the CMU `CodeAgent`, alter any assignment submission interface, or change the evaluator. Each run creates a fresh task Docker container, installs a pinned OpenCode **v1** executable inside `/tmp`, delegates the issue via `opencode run`, and extracts a source-only `git diff` into `artifacts/`. The resulting patch can be graded by the original evaluator on a separate clean container.

The controller runs in Codespaces. **OpenCode executes inside the disposable task container**, not on the Codespaces host. Model inference goes over the network to your chosen provider. No Modal subscription or extra server is needed.

## First run in Codespaces

```bash
uv sync
# Confirm Docker is running, and that the installer can download OpenCode.
uv run python scripts/run_opencode.py --smoke-install
# Fetch the pinned chess source (only once) if you have not already.
bash scripts/bootstrap_sources.sh
# Run the chess coding task with OpenAI (set OPENAI_API_KEY in Codespaces Secrets).
uv run python scripts/run_opencode.py \
  --task tasks/chess-terminal-move --model openai/gpt-5-mini
# Evaluate the resulting patch using the original grader.
uv run python scripts/evaluate.py \
  --task tasks/chess-terminal-move \
  --evaluation tasks/chess-terminal-move/public_tests \
  --patch artifacts/opencode-chess-terminal-move.patch
```

To run a vendored SWE-bench task:

```bash
uv run python scripts/run_opencode.py \
  --instance django__django-15368 --model openai/gpt-5-mini
uv run python scripts/evaluate_swebench.py django__django-15368 \
  --patch artifacts/opencode-django__django-15368.patch
```

To try a free OpenCode provider model, choose a **currently available** `opencode/<model-id>` using OpenCode's model catalog. Free model access, model names, and quotas are not guaranteed, and some models require `OPENCODE_API_KEY` or provider setup. The default here uses your paid OpenAI API key to make initial debugging reproducible.

## Security and limits

- Only a small allowlist of API-key variables is forwarded, and **only to the OpenCode process**. The Docker image build, installation and git commands do not receive these keys. Nevertheless, coding agents and untrusted repository instructions can potentially read or leak credentials. Use a restricted, revocable key and trusted task repos.
- OpenCode is **installed at runtime**, so each run downloads its pinned release. This keeps the original images unchanged, but requires outbound internet access and compatible Linux libraries. If the download or binary cannot execute, the run fails cleanly. The runner supports Linux x86-64 and ARM64.
- The original sandbox is a Docker process isolation boundary, **not a hardened security VM**; do not point it at hostile code or grant sensitive credentials.
- Runs can be costly in tokens and Docker resource usage. Defaults are a 20-minute agent timeout plus setup, a pinned v1 release, and an isolated testbed per attempt.
- Test and fixture changes, `.opencode` state, `AGENTS.md`, and `patch.txt` are excluded from output patches. OpenCode's JSON event output is stored under ignored `artifacts/` and may contain excerpts of the task repository. The runner redacts exact values of forwarded API keys on a best-effort basis; other sensitive content may remain. Do not publish logs without reviewing them.
- These logs are **not** the assignment's native `CodeAgent` trajectories and do not replace required CMU grading artifacts.
- This is a smoke-tested-by-unit-tests integration scaffold, **not** a verified end-to-end Docker/API benchmark until you run it in Codespaces.

## CLI switches

- `--version 1.19.2`: pin the v1 OpenCode release (not OpenCode v2).
- `--model openai/gpt-5-mini`: select provider/model; also supports `OPENCODE_MODEL`.
- `--timeout 1200`: maximum seconds allowed for the OpenCode process.
- `--patch-output path`, `--trajectory path`: choose output locations instead of `artifacts/` defaults.
- `--smoke-install`: validate OpenCode installation without sending a model request.

For integration failure diagnosis, run `uv run pytest -q tests/test_opencode_runner.py` and inspect the Docker daemon, the container's outbound connectivity, and the provider's model/auth settings.
