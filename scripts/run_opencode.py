"""Run the optional OpenCode backend against a chess task or SWE-bench instance.

Free-only by default: the model must be an OpenCode free model
(``opencode/<id>-free``), no API key is forwarded into the sandbox, and the run
refuses to start if anything credential-like is visible inside it. A paid
provider model needs the explicit ``--allow-paid-model`` flag.

Examples:
    uv run python scripts/run_opencode.py --smoke-install
    uv run python scripts/run_opencode.py --probe
    uv run python scripts/run_opencode.py --task tasks/chess-terminal-move
    uv run python scripts/run_opencode.py --instance django__django-15368
    # Paid provider model, credentials forwarded deliberately:
    uv run python scripts/run_opencode.py --task tasks/chess-terminal-move \
        --model openai/gpt-5-mini --allow-paid-model
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from assignment.env import Environment
from assignment.eval.instances import load as load_instance
from assignment.opencode_runner import (
    DEFAULT_FREE_MODEL, DEFAULT_OPENCODE_VERSION, DEFAULT_TIMEOUT, OpenCodeRunError,
    OpenCodeRunner, credentials_from_host, is_free_opencode_model, redact_credentials,
)
from assignment.task import Task
from assignment.utils.image import build_testbed_image


def select_credentials(model: str, allow_paid: bool) -> dict[str, str]:
    """Free models never receive credentials; paid ones only with explicit opt-in."""
    if is_free_opencode_model(model):
        return {}
    if not allow_paid:
        raise SystemExit(
            f'{model!r} is not an OpenCode free model (opencode/<id>-free). '
            'Pass --allow-paid-model to forward API credentials deliberately.'
        )
    return credentials_from_host()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--task', type=Path, help='Local chess task folder')
    group.add_argument('--instance', help='Vendored SWE-bench instance ID')
    group.add_argument('--smoke-install', action='store_true',
                       help='Install and print OpenCode version, without making a model request')
    group.add_argument('--probe', action='store_true',
                       help='Send one trivial "Reply READY" request to check the model has quota')
    parser.add_argument('--model', default=os.getenv('OPENCODE_MODEL', DEFAULT_FREE_MODEL),
                        help='OpenCode provider/model ID (default: %(default)s)')
    parser.add_argument('--allow-paid-model', action='store_true',
                        help='Permit a non-free model and forward allowlisted API keys')
    parser.add_argument('--version', default=DEFAULT_OPENCODE_VERSION,
                        help='Pinned OpenCode v1 version')
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument('--probe-timeout', type=int, default=120)
    parser.add_argument('--patch-output', type=Path)
    parser.add_argument('--trajectory', type=Path)
    args = parser.parse_args()

    credentials = select_credentials(args.model, args.allow_paid_model)
    free_only = not credentials and is_free_opencode_model(args.model)
    print('Model:', args.model, flush=True)
    print('Free-only:', 'yes' if free_only else 'NO', flush=True)
    print('Credential variables provided:', ', '.join(sorted(credentials)) or '(none)', flush=True)

    # The smoke image comes with Python and needs no task checkout.
    if args.smoke_install or args.probe:
        with Environment(image='python:3.12-slim', cwd='/',
                         deployment_timeout=900, runtime_timeout=400) as env:
            runner = OpenCodeRunner(env, model=args.model, version=args.version,
                                    credential_env=credentials, free_only=free_only)
            if args.smoke_install:
                print('OpenCode installed:', runner.install())
                return 0
            probe = runner.probe(timeout=args.probe_timeout)
        print('Probe status:', probe['status'], f"(exit {probe['returncode']})")
        if probe['status'] != 'ok':
            print(redact_credentials(probe['output'], credentials)[-1500:])
        return 0 if probe['status'] == 'ok' else 1

    allowed_paths = None
    if args.task:
        task = Task.load(args.task)
        spec = json.loads((task.root / "task.json").read_text())
        if "editable_paths" in spec:
            paths = spec["editable_paths"]
            if not isinstance(paths, list) or not all(
                isinstance(p, str) for p in paths
            ):
                raise ValueError("editable_paths must be strings")
            allowed_paths = tuple(paths)
        image = build_testbed_image(task)
        issue, label, conda_env = task.problem_statement, task.id, None
    else:
        instance = load_instance(args.instance)
        image = instance.image
        issue, label, conda_env = instance.problem_statement, instance.instance_id, 'testbed'

    patch_file = args.patch_output or Path('artifacts') / f'opencode-{label}.patch'
    log_file = args.trajectory or Path('artifacts') / f'opencode-{label}-run.json'
    print('Image:', image, flush=True)

    record = {
        'task_id': label,
        'backend': 'opencode',
        'model': args.model,
        'opencode_version': args.version,
        'free_only': free_only,
        'credential_variables_forwarded': sorted(credentials),
    }
    started = time.monotonic()
    try:
        # No secret is passed to Environment's constructor or Docker build. Only
        # the agent process receives credentials, and only in paid mode.
        with Environment(image=image, cwd='/testbed', conda_env=conda_env,
                         runtime_timeout=max(args.timeout, 600),
                         deployment_timeout=max(args.timeout + 600, 1800)) as env:
            result = OpenCodeRunner(env, model=args.model, version=args.version,
                                    timeout=args.timeout, credential_env=credentials,
                                    allowed_paths=allowed_paths,
                                    free_only=free_only).run(issue)
    except OpenCodeRunError as exc:
        record.update(status=exc.status, exit_code=exc.returncode, error=str(exc)[-3000:],
                      wall_seconds=round(time.monotonic() - started, 1),
                      events=redact_credentials(exc.output, credentials))
        _write(log_file, record)
        print(f'OpenCode run did not produce a patch: {exc.status}', file=sys.stderr)
        print('OpenCode log:', log_file)
        return 1

    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_text(result.patch)
    # JSON events may contain private source or accidentally echo secrets.
    # Redact known key values and keep artifacts/ untracked and private.
    record.update(status='ok', exit_code=result.command_returncode,
                  wall_seconds=round(time.monotonic() - started, 1),
                  events=redact_credentials(result.output, credentials))
    _write(log_file, record)
    print('Patch:', patch_file)
    print('OpenCode log:', log_file)
    print('Evaluate with existing assignment evaluator:')
    if args.instance:
        print('  uv run python scripts/evaluate_swebench.py', label, '--patch', patch_file)
    else:
        print('  uv run python scripts/evaluate.py --task', args.task,
              '--evaluation', args.task / 'public_tests', '--patch', patch_file)
    return 0


def _write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
