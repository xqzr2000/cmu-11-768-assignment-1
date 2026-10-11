# Publishing / updating the single CMU GitHub repository

The `cmu-11-768-assignment-1` repository is now self-contained with respect to its Docker runtime. You do **not** need to publish, clone, tag, or run `russells-agent-sandbox` anymore. Please review CMU material redistribution rights before public publication.

Read `UPDATE_GITHUB.md` for browser-based upload to an **existing** GitHub repository, including hidden files and removal of obsolete old files.

After updating, open or rebuild the **CMU** repository Codespace:

```bash
uv lock                  # when network is available; commit the root uv.lock
make setup               # checks out pinned chess source, uv sync
make sandbox-doctor
make sandbox-smoke
make test
make test-docker
```

The separate `russells-agent-sandbox` repository can then be archived or deleted *after* the merged CMU repo passes the tests. The OpenAI key belongs only in Codespaces secrets or ignored `.env`, never in the GitHub files.
