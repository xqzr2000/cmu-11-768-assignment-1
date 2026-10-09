# Publishing the two GitHub repositories

These two directories are **prepared source repositories**, not pre-published GitHub projects. The sandbox repo is independently MIT-licensed. The CMU materials have no license in the supplied archive, so obtain authorization or review redistribution rights **before making the harness public**.

## Publish using the GitHub website (recommended)

1. Create **`russells-agent-sandbox`** as a new repository on GitHub. Keep the repository empty (do not initialize a README, license, or .gitignore).
2. Extract `russells-agent-sandbox.zip` locally; use **Add file → Upload files** to upload the *contents* of the extracted folder into the repository root. Ensure `.devcontainer/` and `.github/` are present. Commit to `main`.
3. In the sandbox repository, create and publish the **`v0.1.0`** Git release/tag from `main` (**Releases → Draft a new release**). The harness clones this exact tag, so this is required before starting its Codespace.
4. Create **`cmu-11-768-assignment-1`** under the *same GitHub owner*. Check CMU material redistribution permissions before making the repository public. Upload the extracted folder contents to the root, including hidden files/folders, and commit to `main`.
5. Verify the repos are named exactly as above. No GitHub URL or GitHub username needs to be hard-coded: the harness bootstrap discovers the owner from `origin` in GitHub Codespaces and CI uses `github.repository_owner`.

**Important:** Web uploads do not automatically publish Git tags; publishing the sandbox's `v0.1.0` release is a separate step. The Python distribution is still named `agent-sandbox-runtime`; do not rename that in either `pyproject.toml`.

## Alternative: Publish from the GitHub CLI (same user / organization)

The following commands require an authenticated GitHub CLI (`gh auth login`) and Git identity (`git config user.name` / `user.email`). Unzip both repos into sibling directories.

```bash
cd russells-agent-sandbox
git init -b main
git add . && git commit -m "Initial standalone Docker sandbox runtime"
gh repo create russells-agent-sandbox --public --source=. --remote=origin --push
git tag v0.1.0
git push origin v0.1.0

cd ../cmu-11-768-assignment-1
git init -b main
git add . && git commit -m "Migrate agent harness from Modal to Docker runtime"
gh repo create cmu-11-768-assignment-1 --public --source=. --remote=origin --push
```

When a repo already exists, add its GitHub remote and push with `git push -u origin main` instead of creating it. The harness assumes the sandbox repo is under the *same owner*. If not, set `SANDBOX_RUNTIME_GIT_URL` during bootstrap and update `.github/workflows/tests.yml` for the correct owner.

## Verify both projects

1. Start a Codespace for the **sandbox repository**, and run `make doctor && make test && make test-docker`.
2. Start a separate Codespace for the **harness repository** (you do **not** need to keep the sandbox Codespace running). The bootstrap pulls the sandbox repo as a sibling Python dependency into the harness Codespace.
3. Add the OpenAI API key to GitHub Codespaces repository secrets (`OPENAI_API_KEY`) if not already available; `OPENAI_MODEL` is optional if configured in `.env`.
4. Run `make sandbox-doctor && make doctor && make test && make test-docker` from the harness Codespace. Then run one small agent experiment using your API budget. Verify SWE-bench separately; this may require more resources.
5. On a network-enabled machine, generate and commit fresh `uv.lock` files in both repositories (`uv lock` then `git add uv.lock && git commit ...`). Lock generation was not possible in the artifact-building environment.
6. Check the GitHub Actions logs. The harness actions depend on the sandbox release tag `v0.1.0`, so publish/tag it first.

## Version contract

The harness `pyproject.toml` pins runtime dependency `==0.1.0` and points it at `../russells-agent-sandbox` for local source installation. `scripts/bootstrap_sandbox.sh` clones `v0.1.0` when it is absent. When publishing a new runtime version, update all three places: runtime package version + release tag; harness dependency version + bootstrap tag; harness CI checkout tag. Run both repos' unit and container tests again before release.

## Local VS Code

Use **Dev Containers: Reopen in Container** from either repo folder with Docker Desktop running. The default configuration uses Docker-in-Docker for consistent Codespaces/local behavior, so no extra sandbox server is required. For a source edit shared across both repos, open the harness with `russells-agent-sandbox` cloned beside it and reopen the container.
