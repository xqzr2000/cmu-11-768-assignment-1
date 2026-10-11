# Migration: Modal → Docker, then two repos → one uv workspace

The original CMU assignment uses Modal and SWE-ReX. This adaptation uses local Docker containers managed by `agent-sandbox-runtime`, now bundled in `packages/agent-sandbox-runtime/`.

| Earlier design | Merged design |
| --- | --- |
| `russells-agent-sandbox` in a sibling GitHub checkout | `packages/agent-sandbox-runtime/` inside CMU repo |
| `scripts/bootstrap_sandbox.sh` clones a tagged repo | Compatibility script simply checks that the package is present; no clone |
| `../russells-agent-sandbox` source in root `pyproject.toml` | `agent-sandbox-runtime = { workspace = true }` and `[tool.uv.workspace]` |
| Two GitHub Actions CI pipelines | One root workflow tests both packages |
| Two independent dependency resolutions | One root `uv.lock` (regenerate with `uv lock`) |
| Modal image builder and deployment | `DockerImage` and `Sandbox` managed by local Docker engine |
| Modal public tunnel | Docker localhost-only ephemeral port mapping |

`assignment.env.Environment`, the chess tools and the evaluation harness still use the same Python adapter interface. Only packaging / setup paths changed in this merge.

## Limits

The sandbox uses Docker containers, not hardened VMs. Sandbox images need Bash and GNU `timeout`. `output` combines stdout and stderr in order, rather than preserving their original cross-stream interleaving. Image pulls / Docker network / the pinned chess app checkout require internet initially. SWE-bench published image CPU architecture compatibility must be checked, especially on ARM Macs.

`ASSIGNMENT.md` remains the historical course instructions (and may still mention Modal). Follow `README.md` for this adaptation's setup.
