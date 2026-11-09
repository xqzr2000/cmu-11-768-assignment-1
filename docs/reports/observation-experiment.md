# Observation A/B experiment: board only vs board + legal moves

Each run plays White against the server's deterministic Black bot through
`play_move`. The two conditions differ in one thing: whether observations and the
system prompt include the `legal_moves` list. The board diagram, FEN and recent
history are always shown.

**Setup (Nov 9, 2026).**

- **Models.** "DeepSeek" = `deepseek-flash` (DeepSeek-V4.1-Flash, `api.deepseek.com`).
  The second model slot, whose files keep the official `gpt-oss` names, ran
  **`gpt-5-mini`** (OpenAI) in place of GPT-OSS-120b.
- **Run length.** Every run was cut to **15 ReAct steps** (instead of 200) to save time,
  so no game reached a terminal state.
- **Run options.** All four runs used `AGENT_STRIP_REASONING=1` and a 2-hour sandbox.

**Counting.** "Rejected as illegal" counts `play_move` calls the chess server
refused, including one refused by its request schema (see below). "Other invalid"
counts calls that failed before reaching the server. Invalid-move rate =
(illegal + other invalid) / total `play_move` calls.

| Model | Observation | `play_move` calls | Rejected as illegal | Other invalid | Invalid-move rate | `game_over: true` | Final status | Plies played | ReAct steps |
|---|---|---:|---:|---:|---:|---|---|---:|---:|
| DeepSeek | board only | 15 | 0 | 0 | 0.0% | no | Your turn | 30 | 15 |
| DeepSeek | board + legal moves | 15 | 0 | 0 | 0.0% | no | Your turn | 30 | 15 |
| gpt-5-mini | board only | 15 | 3 | 0 | 20.0% | no | Your turn | 24 | 15 |
| gpt-5-mini | board + legal moves | 15 | 0 | 0 | 0.0% | no | Your king is in check | 30 | 15 |

## The three rejected moves (gpt-5-mini, board only)

| White's move no. | Move sent | Kind of error | What went wrong |
|---:|---|---|---|
| 8 | `c2cxd3` | **Notation** | The model mixed algebraic capture notation (`x`) into UCI. The intended move was c2×d3, i.e. `c2d3`. The request schema rejected it as too long before any chess rule was checked. |
| 9 | `e1e2` | **Stale board state** | It tried to move the king from e1, but White had already castled: the FEN shows the king on g1 and e1 empty. |
| 9 (retry) | `c4d4` | **Piece movement** | It tried to move the bishop on c4 sideways to d4, where Black's queen stood. A bishop can't move that way. |

None of the three came while White was in check.

## Pace and thinking cost

| Run | Seconds per step | Output tokens per step |
|---|---:|---:|
| DeepSeek, board only | 12 | 1,277 |
| DeepSeek, board + legal moves | **43** | **7,817** |
| gpt-5-mini, board only | 7 | 480 |
| gpt-5-mini, board + legal moves | 4 | 249 |

## Findings

1. **For gpt-5-mini, listing legal moves removed every illegal move:** 3 of 15 (20%)
   without the list, 0 of 15 with it. All three errors are the kinds the list rules
   out: a notation slip, forgetting that it had castled, and a piece-movement rule.
   Each rejected move cost a step without advancing the game, which is why that run
   played 24 plies instead of 30.
2. **DeepSeek made no illegal moves in either condition.** Over 15 opening and
   middlegame moves, the list made no difference to its move validity.
3. **The errors weren't in check positions.** That contradicts the generic
   expectation in the report template. They clustered in a sharper middlegame (Black's
   queen centralised on d4, a pawn capture on d3) a few moves after White castled.
   Two came back-to-back in the same position. The recoverable `<chess_error>`
   observation let the model correct itself, at the cost of steps.
4. **The legal-move list changed thinking cost in opposite directions.**
   - gpt-5-mini thought about half as much with the list (480 → 249 tokens per step, 7 → 4 s).
   - DeepSeek thought **six times as much** (1,277 → 7,817 tokens, 12 → 43 s).

   One reading: with an explicit menu, DeepSeek works through candidates one by one,
   while gpt-5-mini just picks from it. The positions also differed between runs, so
   this could partly come from the positions themselves.
5. **This explains the slow full-game attempts.** Part 3.1 runs DeepSeek *with* the
   legal-move list, the slowest condition here at ~43 s per step, so a 100-move game
   needs well over an hour.

## Interpretation

Listing legal moves moves the job of legality checking out of the model and into
the tool interface. Choosing a valid action becomes picking a string from the
observation. For a smaller, faster model that sometimes loses track of the board
(gpt-5-mini), that's a clear win in validity and speed. For a model that already
tracks the board reliably (DeepSeek), validity was already perfect, and the list's
effect showed up elsewhere, in much longer deliberation. Observation design
therefore changes more than error rates: it changes how the model spends its
thinking budget. That cost should be measured, not assumed.

## Limitations

- **One run per condition, 15 steps each (at most 30 plies).** These are opening and
  middlegame positions only, no game finished, and a single error changes the rate by
  6.7 points. The results show a direction, not reliable rates.
- **Positions differ between runs.** The Black bot is deterministic, but White's
  choices aren't, so the two conditions didn't face the same positions.
- **Timing depends on the providers.** Seconds per step include API latency and
  provider load.
- **gpt-5-mini replaces GPT-OSS-120b.** The model comparison isn't the one the
  assignment specifies.
- **One "illegal" move is a format error.** `c2cxd3` was rejected by request
  validation, not by a chess rule, but it counts in the invalid-move rate either way.
