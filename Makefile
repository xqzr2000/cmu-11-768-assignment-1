.PHONY: setup doctor verify-sources test test-docker test-chess-docker check-part1 check-swebench \
	run-code-agent run-swebench-agent run-chess-agent \
	run-obs-experiment-no-legal-moves run-obs-experiment-legal-moves \
	run-obs-deepseek-no-legal run-obs-deepseek-legal \
	run-obs-gpt-oss-no-legal run-obs-gpt-oss-legal \
	run-chess-sandbox instructor-eval-base instructor-eval-gold instructor-eval-patch \
	run-python-skill-agent report-tokens report-obs package

TASK ?= tasks/chess-terminal-move
CODE_SKILLS ?= tasks/code-skills
PATCH ?= artifacts/fix.patch
PART1_TRAJECTORY ?= artifacts/part1-trajectory.json
PRIVATE_EVAL ?= .private/chess-terminal-move
PUBLIC_EVAL ?= $(TASK)/public_tests
# One of the vendored instances under tasks/swebench/.
INSTANCE ?= django__django-15368
SWEBENCH_PATCH ?= artifacts/$(INSTANCE).patch
SWEBENCH_TRAJECTORY ?= artifacts/$(INSTANCE)-trajectory.json
TRAJECTORY ?= artifacts/part3-trajectory.json
RESULT ?= artifacts/game-result.json
# Read one KEY from .env (ignoring comments). An exported environment variable
# or a `make VAR=...` argument still wins over the file.
dotenv = $(strip $(shell sed -n 's/^$(1)=//p' .env 2>/dev/null | sed -e 's/[[:space:]]*\#.*//' -e 's/^["'"'"']//' -e 's/["'"'"']$$//' | tail -n 1))
# Empty MODEL means "use OPENAI_MODEL from the environment / .env".
MODEL ?=
MODEL_FLAG = $(if $(strip $(MODEL)),--model $(MODEL),)
DEEPSEEK_MODEL ?= $(or $(call dotenv,DEEPSEEK_MODEL),deepseek/deepseek-v4-flash-0731)
GPT_OSS_MODEL ?= $(or $(call dotenv,GPT_OSS_MODEL),openai/gpt-oss-120b)
MODEL_TAG ?= $(or $(subst /,-,$(strip $(MODEL))),default)
COMPACT_THRESHOLD ?= 6000
STEPS ?= 200
CHESS_TIMEOUT ?= 1800
OBS_NO_LEGAL_TRAJECTORY ?= artifacts/part3-no-legal-moves-$(MODEL_TAG).json
OBS_LEGAL_TRAJECTORY ?= artifacts/part3-legal-moves-$(MODEL_TAG).json
OBS_NO_LEGAL_RESULT ?= artifacts/part3-no-legal-moves-$(MODEL_TAG)-result.json
OBS_LEGAL_RESULT ?= artifacts/part3-legal-moves-$(MODEL_TAG)-result.json

setup:
	bash scripts/bootstrap_sandbox.sh
	uv sync
	bash scripts/bootstrap_sources.sh
	$(MAKE) verify-sources

doctor:
	uv run assignment-doctor

verify-sources:
	uv run python -c "from assignment.task import Task; from assignment.utils.image import verify_source; verify_source(Task.load('tasks/chess-terminal-move'))"

# Fast and offline: runs unit tests without a Docker daemon or OpenAI API calls.
test:
	uv run pytest

# Runs real containers and may pull images (requires Docker).
test-docker:
	uv run pytest -m docker

test-chess-docker:
	uv run pytest -m docker tests/test_chess_sandbox.py

# Apply the student's generated patch to a fresh testbed and run the public
# Part 1 regression test plus the existing chess-app suite.
check-part1:
	@test -f "$(PATCH)" || (echo "Patch not found: $(PATCH). Run make run-code-agent first."; exit 1)
	uv run python scripts/evaluate.py --task $(TASK) --evaluation $(PUBLIC_EVAL) \
		--patch $(PATCH) -v

# Apply a patch to the published SWE-bench image for INSTANCE and grade it
# against that instance's FAIL_TO_PASS and PASS_TO_PASS tests.
check-swebench:
	@test -f "$(SWEBENCH_PATCH)" || (echo "Patch not found: $(SWEBENCH_PATCH). Run make run-swebench-agent INSTANCE=$(INSTANCE) first."; exit 1)
	uv run python scripts/evaluate_swebench.py $(INSTANCE) --patch $(SWEBENCH_PATCH) -v

run-code-agent:
	uv run assignment-code-agent --task $(TASK) $(MODEL_FLAG) --step-limit $(STEPS) \
		--skills-path $(CODE_SKILLS) --trajectory $(PART1_TRAJECTORY) \
		--patch-output $(PATCH)

# Run the code agent on a vendored SWE-bench instance, in its published image.
run-swebench-agent:
	uv run assignment-swebench-agent $(INSTANCE) $(MODEL_FLAG) \
		--patch-output $(SWEBENCH_PATCH) \
		--trajectory $(SWEBENCH_TRAJECTORY) \
		--skills-path $(CODE_SKILLS) \
		--step-limit $(STEPS) $(if $(filter-out 0,$(COMPACT_THRESHOLD)),--compact-threshold-tokens $(COMPACT_THRESHOLD),)

run-chess-agent:
	uv run assignment-play-chess $(MODEL_FLAG) --task $(TASK) --patch $(PATCH) \
		--step-limit $(STEPS) --sandbox-timeout $(CHESS_TIMEOUT) \
		--trajectory $(TRAJECTORY) --result $(RESULT)

run-obs-experiment-no-legal-moves:
	uv run assignment-play-chess $(MODEL_FLAG) --task $(TASK) --patch $(PATCH) \
		--omit-legal-moves --step-limit $(STEPS) --sandbox-timeout $(CHESS_TIMEOUT) \
		--trajectory $(OBS_NO_LEGAL_TRAJECTORY) --result $(OBS_NO_LEGAL_RESULT)

run-obs-experiment-legal-moves:
	uv run assignment-play-chess $(MODEL_FLAG) --task $(TASK) --patch $(PATCH) \
		--step-limit $(STEPS) --sandbox-timeout $(CHESS_TIMEOUT) \
		--trajectory $(OBS_LEGAL_TRAJECTORY) --result $(OBS_LEGAL_RESULT)

run-obs-deepseek-no-legal:
	$(MAKE) run-obs-experiment-no-legal-moves MODEL="$(DEEPSEEK_MODEL)" MODEL_TAG=deepseek

run-obs-deepseek-legal:
	$(MAKE) run-obs-experiment-legal-moves MODEL="$(DEEPSEEK_MODEL)" MODEL_TAG=deepseek

run-obs-gpt-oss-no-legal:
	$(MAKE) run-obs-experiment-no-legal-moves MODEL="$(GPT_OSS_MODEL)" MODEL_TAG=gpt-oss

run-obs-gpt-oss-legal:
	$(MAKE) run-obs-experiment-legal-moves MODEL="$(GPT_OSS_MODEL)" MODEL_TAG=gpt-oss

run-chess-sandbox:
	uv run assignment-chess-sandbox --task $(TASK) --sandbox-timeout $(CHESS_TIMEOUT) $(if $(wildcard $(PATCH)),--patch $(PATCH),)
# Programmatic tools + chess skill run (Part 3.5).
run-python-skill-agent:
	uv run assignment-play-chess $(MODEL_FLAG) --task $(TASK) --patch $(PATCH) \
		--programmatic-tools --skills-path tasks/chess-skills \
		--step-limit $(STEPS) --sandbox-timeout $(CHESS_TIMEOUT) \
		--trajectory artifacts/part3-python-skill-trajectory.json \
		--result artifacts/part3-python-skill-result.json

# Offline, free: summarize saved trajectories into the Part 2/3 report tables.
report-tokens:
	uv run python scripts/report_token_usage.py

report-obs:
	uv run python scripts/report_observation_experiment.py

# Build the submission ZIP (src/, artifacts/, AI_USAGE.md), never .env.
package:
	uv run python scripts/package_submission.py

.PHONY: sandbox-doctor sandbox-smoke
sandbox-doctor:
	uv run agent-sandbox doctor
sandbox-smoke:
	uv run agent-sandbox smoke
