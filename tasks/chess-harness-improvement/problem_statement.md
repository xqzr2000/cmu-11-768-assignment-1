# Improve ChessAgent Tool-Call Safety

## Background

The chess agent is a ReAct agent that uses an LLM
to select moves and interact with chess tools.

## Problem

ChessAgent.execute_tool_calls prevents multiple
board-changing actions in one LLM response.

However, it currently allows simulate_move after
play_move or run_python, even though the board
may already have changed.

## Objective

Reject simulate_move calls that occur after a
board-changing action in the same response.

## Requirements

- Edit only src/assignment/agent/chess_agent.py.
- Preserve the existing ReAct loop and LLM.
- Preserve play_move and run_python behavior.
- Allow multiple simulate_move calls before a board change.
- Preserve tool_call_id in returned messages.
- Return a useful chess_error for rejected calls.
- Do not implement chess search algorithms or Stockfish.
- Do not modify tests, fixtures, prompts, or the server.

Make the smallest correct source-code change.
Run relevant existing tests after the modification.
