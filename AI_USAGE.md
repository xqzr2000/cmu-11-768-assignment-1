# AI usage

> Review and edit this file so it accurately describes how *you* used AI tools.

## Tools used

- **Claude (Anthropic), via claude.ai** — used to implement the assignment's code TODOs and supporting tooling.

## How it was used

- Implemented the TODOs in `src/assignment/agent/` (`base.py`, `code_agent.py`, `chess_agent.py`, `chess_tools.py`, `tools.py`): the shared ReAct loop and prompt construction, skill loading, the coding-agent tools, context compaction, and the chess tools (`play_move`, `simulate_move`, `run_python`, `invoke_skill`).
- Wrote a dev container configuration, provider-agnostic `.env.example`, Makefile changes so runs use the model from `.env`, and offline scripts that tabulate trajectory statistics for the two reports and package the submission.
- Checked the implementation with the public tests and with additional offline checks against a locally running chess server.

The billable runs (Modal sandboxes and LLM calls that produce the patches, trajectories and results) were run by me. <!-- edit: describe what you ran, reviewed, and changed yourself, and how you edited the report prose -->
