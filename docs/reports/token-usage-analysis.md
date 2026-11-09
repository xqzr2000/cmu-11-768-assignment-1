# Token usage: context compaction vs full context (django__django-15368)

Both runs use the same harness, model (`deepseek-flash`, DeepSeek-V4.1-Flash) and
task. Only the compaction setting differs, and **both patches resolved the issue**
(FAIL_TO_PASS 1/1, PASS_TO_PASS 29/29) with the same fix:
`isinstance(attr, Expression)` → `hasattr(attr, 'resolve_expression')` in
`QuerySet.bulk_update()`, plus removing the now-unused `Expression` import.

- Compacted (`COMPACT_THRESHOLD=6000`): `artifacts/django__django-15368-trajectory.json`
- Full context (`COMPACT_THRESHOLD=0`): `artifacts/django__django-15368-baseline-trajectory.json`

Token counts are the provider-reported `usage` of every request, including the two
extra summarisation requests compaction made. "Estimated" figures come from the
harness's character-based estimate at compaction time.

## Summary

| Metric | Compacted | Full context | Change |
|---|---:|---:|---:|
| ReAct steps (action requests) | 20 | 19 | +5.3% |
| Prompt tokens, action requests | 90,211 | 135,766 | -33.6% |
| Completion tokens, action requests | 5,387 | 4,717 | +14.2% |
| Compaction requests | 2 | 0 | n/a |
| Prompt tokens, compaction requests | 8,433 | 0 | n/a |
| Completion tokens, compaction requests | 1,772 | 0 | n/a |
| **Total tokens billed** | 105,803 | 140,483 | -24.7% |
| Peak prompt size (one request) | 5,976 | 11,400 | -47.6% |
| Mean prompt size per request | 4,511 | 7,146 | -36.9% |
| Final prompt size | 5,853 | 11,400 | -48.7% |
| Cached prompt tokens reported | 80,896 | 128,896 | -37.2% |
| **Uncached prompt tokens** (all prompt − cached) | **17,748** | **6,870** | **+158%** |
| Share of prompt tokens served from cache | 82% | 95% | |

## Compaction events

| Compaction | Before step | Est. tokens before | Est. tokens after | Reduction |
|---:|---:|---:|---:|---:|
| 1 | 8 | 5,576 | 1,907 | -65.8% |
| 2 | 15 | 6,109 | 2,387 | -60.9% |

## What the numbers show

**1. The prompt follows a saw-tooth instead of a ramp.** In a ReAct loop every
request re-sends the whole history. Without compaction, the prompt grew steadily
from 1,844 to 11,400 tokens, about 530 tokens per step: the previous prompt plus
the newest action and observation. With compaction, the prompt climbed to the
6,000 threshold, dropped to ~2,900 after the first summary (5,715 → 2,911) and to
~3,400 after the second (5,976 → 3,395), then climbed again. So the peak was
nearly halved, and the cumulative prompt tokens, which grow roughly quadratically
without compaction, fell by a third.

**2. Fewer tokens, but more of them uncached.** Even after paying 10,205 tokens
for the two summaries, compaction billed 24.7% fewer tokens. The cache columns,
though, point the other way.

- The full-context prompt only ever grows *at the end*, so each request starts with
  exactly the previous request's tokens, and **95%** of its prompt tokens were cache
  hits.
- Each compaction **rewrites the start of the prompt** (system + task + new working
  memory). The cached prefix then no longer matches, so the compacted run had
  **2.6× as many uncached prompt tokens** (17,748 vs 6,870).

If cached input tokens cost a fraction *r* of normal input, compaction is cheaper
on input only when 17,748 + 80,896·*r* < 6,870 + 128,896·*r*, i.e. when ***r* > ~0.23**.
Providers commonly discount cache hits far more steeply than that, which would make
this run's input *more* expensive with compaction. It also generated more output
(7,159 vs 4,717 completion tokens, counting the summaries). So "−25% tokens" doesn't
mean "−25% cost": on a 20-step task with good caching, compaction roughly breaks
even at best. Check your provider's actual cache pricing before quoting a dollar
figure.

**3. The working memory was good enough that nothing was lost.** The second
summary kept everything TODO 2.1 asks for:

- the objective and constraints;
- the exact file and line (`query.py` ~673);
- both edits (`isinstance` → `hasattr`, the import cleanup) and the regression test added;
- the commands and their results (`Ran 30 tests … OK`, `Ran 597 tests … OK`);
- a blocker that had already come up ("flake8/isort not installed");
- the next action.

After compacting, the agent didn't re-read files or repeat commands, and it took
one more step than the baseline (20 vs 19).

**4. Behaviour differed in one interesting way.** Only the full-context run put the
bug back to confirm its new test failed without the fix (step 13), then re-applied
the fix. With one run per condition, this can't be attributed to compaction.

## Trade-offs

- **Context headroom vs extra calls.** Compaction keeps every later request small,
  which is what makes long tasks possible at all. The Part 3 chess attempt reached
  313k-token prompts without it. Each compaction is an extra model call that reads
  the old history, though. On a short task like this one, it fired twice and its cost
  was a tenth of the total.
- **Prompt caching works against compaction.** A prompt that only grows at the end is
  ideal for prefix caching. Compaction gives up most of that discount every time it
  rewrites the prefix. The cheaper cache hits are, the longer a run must be before
  compaction pays for itself.
- **Lossy memory.** The summary keeps what the summariser judged important. This
  run's summary was complete, but exact tool output is gone. A detail that only
  matters later (an exact error message, a line number that shifted) would have to be
  re-read, adding steps.
- **Focus.** A short prompt without stale test output keeps the current state in
  front of the model. The full-context agent can always look back at the raw
  evidence, which may be why it chose to re-verify the fix.

**Bottom line:** compaction is primarily a **capacity** tool (keeping long runs
inside the context window and fast) rather than a cost tool. On this 20-step
task it cut tokens by a quarter, but given cache pricing it probably saved little
or no money.

<details>
<summary>Per-step prompt tokens</summary>

| Step | Compacted prompt tokens | Baseline prompt tokens |
|---:|---:|---:|
| 1 | 1,844 | 1,844 |
| 2 | 2,930 | 3,011 |
| 3 | 3,313 | 4,304 |
| 4 | 4,046 | 5,038 |
| 5 | 5,053 | 5,440 |
| 6 | 5,587 | 5,665 |
| 7 | 5,715 | 5,796 |
| 8 | 2,911 | 6,060 |
| 9 | 3,626 | 6,260 |
| 10 | 4,414 | 7,047 |
| 11 | 4,623 | 7,539 |
| 12 | 5,418 | 7,864 |
| 13 | 5,612 | 8,713 |
| 14 | 5,976 | 9,055 |
| 15 | 3,395 | 9,401 |
| 16 | 4,447 | 9,694 |
| 17 | 4,902 | 10,631 |
| 18 | 5,089 | 11,004 |
| 19 | 5,457 | 11,400 |
| 20 | 5,853 | |

</details>
