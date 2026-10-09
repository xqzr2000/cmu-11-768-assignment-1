# Migration notes: Modal -> local Docker runtime

The original assignment uses Modal and SWE-ReX's Modal deployment. This fork uses the standalone `russells-agent-sandbox` repository as a Docker backend and preserves the synchronous Environment API used by the code agent, chess agent, and evaluator.

| Original | Adaptation |
| --- | --- |
| `modal.Image.from_dockerfile` | immutable `DockerImage.from_dockerfile` image recipe |
| Modal `.pip_install(...)` | last Docker build layer for `task.pins` |
| Modal `.add_local_file(...)` | Docker build layer `COPY` for permitted injected assignment files |
| SWE-ReX Modal runtime | `Sandbox.execute(...)` using `docker exec` and GNU timeout |
| Modal tunnel | loopback-only ephemeral Docker `-p 127.0.0.1::PORT` |
| `ModalDeployment.stop` | Docker `rm --force` and independent bounded PID 1 |
| Modal credentials | local Docker daemon (Codespaces Docker-in-Docker) |

## Known limits

- This is a Docker container boundary, not a general hostile-code execution service.
- GNU `timeout`, Bash and `/bin/sh` are expected inside images.
- Published SWE-bench image architecture needs validation on ARM Macs.
- Changing the backend changes behavior of full cross-stream ordering and timeout reporting. `output` is stdout followed by stderr, while both streams are available separately.
- `ASSIGNMENT.md` is a historical course document and still mentions Modal. Current adaptation instructions are in `README.md`.
- Full tests need Docker networking, package index access, a chess-app checkout, and (for agent runs) OpenAI API credentials.
