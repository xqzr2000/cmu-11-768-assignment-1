# Preserve the final ChessAgent tool observation

## Evidence

A real ChessAgent experiment used gpt-5-mini for four steps.

The fourth action was play_move("f3e5").
A deterministic replay showed Black replying d5e5,
capturing the knight and checking White's king.

The saved trajectory contained four prompts and four
responses, but did not contain the fourth tool observation.

## Root cause to investigate

The agent saves model-request prompt snapshots.
The last tool result has no following model request,
so it does not appear in those snapshots.

## Objective

Improve the chess CLI's trajectory logging to preserve
the final step's tool observations on step-limit termination.

## Requirements

- Edit only src/assignment/cli.py.
- Do not modify Agent.run or its protected saving block.
- Preserve existing trajectory fields: prompts, responses,
  and compactions.
- Add a final_observations field containing the final
  step's tool observations, including tool_call_id and content.
- Preserve original tool-call ordering.
- Do not fabricate observations or duplicate unrelated steps.
- Preserve the StepLimitError behavior and exit status.
- Preserve normal completed-game behavior.
- Do not modify tests or the chess server.
- Do not make external API calls during testing.

Make the smallest correct change.
Run relevant offline tests.
