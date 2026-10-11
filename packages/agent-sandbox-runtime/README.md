# Agent sandbox runtime (vendored workspace package)

This folder contains the reusable Docker runtime previously maintained in
`russells-agent-sandbox`. It is now part of the CMU assignment's single `uv`
workspace, so it **does not require** a second GitHub repository, Git tag,
Codespace, or remote sandbox server.

- Python distribution: `agent-sandbox-runtime`
- Import: `from agent_sandbox_runtime import Sandbox, DockerImage`
- Console command: `uv run agent-sandbox` (run from the repository root)
- Source code: `src/agent_sandbox_runtime/`
- Tests: `tests/`, included in the root test suite

The package launches isolated task containers using the Docker daemon available
inside the *main CMU devcontainer*. The Python runtime package itself is **not**
a sandbox and does not need a persistent server process.

From the repository root:

```bash
uv sync
make sandbox-doctor
make sandbox-smoke
make test
make test-docker
```

The Docker backend restricts task containers (CPU/memory/process counts, no
host mounts, dropped Linux capabilities, localhost-only published ports), but
Docker isolation is **not** a hardened virtual machine boundary for malicious
code. Avoid exposing sandbox ports publicly or passing secrets into task containers.

The runtime-specific MIT terms are in `LICENSE` in this directory. These terms
**do not** license or replace attribution/rights for the upstream CMU materials.
