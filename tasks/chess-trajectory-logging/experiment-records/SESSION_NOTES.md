# OpenCode Experiment — October 23, 2026

Branch: open-code

## Completed

- Repaired the chess server: 10/10 tests passed.
- Verified OpenCode chess harness improvement: 4/4 tests passed.
- Ran ChessAgent with gpt-5-mini for four steps.
- Collected 5,485 tokens of trajectory telemetry.
- Identified a tactical mistake: f3e5 followed by d5e5.
- Identified missing final tool observations.
- Created the chess-trajectory-logging task.
- Confirmed the original baseline fails two regression tests.
- Ran OpenCode using its free MiMo model.

## OpenCode attempt 1

FAIL_TO_PASS: 1/2
PASS_TO_PASS: 1/1
RESOLVED: no

The generated patch omitted the original "role" field
from final tool observations.

The proposed patch was NOT integrated into cli.py.

## Next session

1. Update the task problem statement with evaluator feedback.
2. Run OpenCode again using the free model.
3. Evaluate the second patch against the same tests.
4. Review the proposed implementation.
5. Apply the accepted fix and repeat the trajectory experiment.

Do not use paid OpenAI models for OpenCode experiments.

## October 24, 2026 — Attempt 2

### Environment

- Branch: open-code
- Base commit: c2e7db78c7fb7a504c61f9d6d46a5cc4d9341369
- Sandbox: restricted local Docker container
- OpenCode version: 1.19.4
- Model: opencode/mimo-v2.6-flash-free
- No paid OpenAI model used for OpenCode execution

### Feedback-driven improvement

Attempt 1 preserved only selected tool-message fields,
omitting the original `role` field.

We added evaluator feedback to problem_statement.md,
then launched a fresh OpenCode session against the same
pinned baseline.

Attempt 2 generated a different implementation using
deepcopy to preserve complete original tool messages.

The updated CLI records final observations in a finally
block around Agent.run(), without changing Agent.run().

### Evaluation

| Evaluation | Attempt 1 | Attempt 2 |
| --- | --- | --- |
| FAIL_TO_PASS | 1/2 | 2/2 |
| PASS_TO_PASS | 1/1 | 1/1 |
| Overall public tests | 2/3 | 3/3 |

Additional attempt 2 validation:

- Broader isolated regression: 15/15 passed
- Repository non-Docker tests: 38/38 passed
- Docker integration tests: 3/3 passed
- Total repository tests: 41/41 passed

### Artifacts

- attempt1.patch: unsuccessful first candidate
- attempt2.patch: validated second candidate
- attempt2.events.jsonl: raw OpenCode execution events
- attempt2.evaluation.txt: targeted regression evaluation
- attempt2.broader-evaluation.txt: broader evaluation

### Conclusions

Evaluator feedback improved the OpenCode-generated harness
from a partially correct candidate to one passing the
complete repository test suite.

The improvement was generated in an isolated sandbox,
tested offline, and then applied to the open-code branch.

This is a manual, Harness2-inspired feedback cycle.
It does not implement Google's automated recursive loop.

### Remaining limitations

- A live LLM-driven chess replay has not yet been repeated
  against the improved implementation.
- Malformed-history and trajectory-write-failure edge cases
  have not been tested directly.
- Free-model availability can change over time.

### Raw execution log retention

The complete attempt 2 OpenCode execution log and its
empty stderr log are retained outside the Git repository
in the Codespace's private experiment backup directory.

The public repository retains the generated patch,
evaluation results, and experiment summary.

The raw log was screened for common credential patterns
but was not comprehensively audited for private content.
