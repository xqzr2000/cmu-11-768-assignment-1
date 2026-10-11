# How to replace the existing GitHub repository through the website

This archive contains the complete **source tree** for `cmu-11-768-assignment-1`, including the runtime in `packages/agent-sandbox-runtime/`. It does not contain the external `chess_app` checkout, secrets, local virtualenv, or build caches.

1. Download and extract the ZIP locally.
2. Open the GitHub repository `xqzr2000/cmu-11-768-assignment-1` and switch to the branch to update (usually `main`).
3. Use **Add file → Upload files**. Drag in the **contents** of the extracted `cmu-11-768-assignment-1` folder, **not** the enclosing folder or the ZIP itself. Include hidden `.github/`, `.devcontainer/`, `.gitignore`, and `.env.example` files; inspect the pending list before committing.
4. Commit the changes. If the uploader does not overwrite existing files, use GitHub's web editor or `github.dev` to edit those files, or use a local Git checkout and push. **Uploading missing files does not delete obsolete files** from the existing repository.
5. Ensure `.github/workflows/tests.yml` has **no checkout of** `russells-agent-sandbox`. The retained `scripts/bootstrap_sandbox.sh` is now only a harmless compatibility check.
6. Open/rebuild the CMU repository Codespace (Command Palette: **Codespaces: Rebuild Container**, or create a fresh Codespace). From the project root run `uv lock`, then `make setup`, `make test`, `make sandbox-doctor`, `make sandbox-smoke`, `make test-docker`. Commit the newly generated **root** `uv.lock` to GitHub.
7. Only after the Codespace passes should you archive or delete `russells-agent-sandbox`. It is not needed by the merged setup.

**Safer way to replace lots of existing files:** Upload via Git from a local checkout; Git tracks deletions and overwrites reliably. A browser upload works for new files, but it can be awkward for nested folders and existing files. `github.dev` or Codespaces' Source Control UI can also commit the merged tree.

Important: If the repository has changed since these ZIP snapshots, review the diff before overwriting those newer GitHub changes. These archive sources were based on your last prepared ZIPs, not verified against the latest remote commits.
