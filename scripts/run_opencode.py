"""Run the optional OpenCode backend against a chess task or SWE-bench instance.

Examples:
    uv run python scripts/run_opencode.py --smoke-install
    uv run python scripts/run_opencode.py --task tasks/chess-terminal-move --model openai/gpt-5-mini
    uv run python scripts/run_opencode.py --instance django__django-15368 --model openai/gpt-5-mini
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from assignment.env import Environment
from assignment.eval.instances import load as load_instance
from assignment.opencode_runner import (
    DEFAULT_OPENCODE_VERSION, DEFAULT_TIMEOUT, OpenCodeRunner, credentials_from_host,
    redact_credentials,
)
from assignment.task import Task
from assignment.utils.image import build_testbed_image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--task', type=Path, help='Local chess task folder')
    group.add_argument('--instance', help='Vendored SWE-bench instance ID')
    group.add_argument('--smoke-install', action='store_true',
                       help='Install and print OpenCode version, without making an API request')
    parser.add_argument('--model', default=os.getenv('OPENCODE_MODEL', 'opencode/mimo-v2.6-flash-free'),
                        help='OpenCode provider/model ID')
    parser.add_argument('--version', default=DEFAULT_OPENCODE_VERSION,
                        help='Pinned OpenCode v1 version')
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument('--patch-output', type=Path)
    parser.add_argument('--trajectory', type=Path)
    args = parser.parse_args()

    # The smoke image comes with Python and needs no task checkout.
    if args.smoke_install:
        with Environment(image='python:3.12-slim', cwd='/',
                         deployment_timeout=900, runtime_timeout=400) as env:
            print('OpenCode installed:', OpenCodeRunner(
                env, model=args.model, version=args.version).install())
        return 0

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
    # No secret is passed to Environment's constructor or Docker build. Only
    # the agent process receives the credential allowlist, when explicitly enabled.
    credentials = (
        {}
        if args.model == 'opencode/mimo-v2.6-flash-free'
        else credentials_from_host()
    )
    print('Image:', image, flush=True)
    print('Model:', args.model, flush=True)
    print('Credential variables provided:', ', '.join(sorted(credentials)) or '(none)', flush=True)
    with Environment(image=image, cwd='/testbed', conda_env=conda_env,
                     runtime_timeout=max(args.timeout, 600),
                     deployment_timeout=max(args.timeout + 600, 1800)) as env:
        result = OpenCodeRunner(env, model=args.model, version=args.version,
                               timeout=args.timeout, credential_env=credentials,
                                allowed_paths=allowed_paths).run(issue)

    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_text(result.patch)
    # JSON events may contain private source or accidentally echo secrets.
    # Redact known key values and keep artifacts/ untracked and private.
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(json.dumps({
        'task_id': label,
        'backend': 'opencode',
        'model': result.model,
        'opencode_version': result.version,
        'exit_code': result.command_returncode,
        'events': redact_credentials(result.output, credentials),
    }, indent=2))
    print('Patch:', patch_file)
    print('OpenCode log:', log_file)
    print('Evaluate with existing assignment evaluator:')
    if args.instance:
        print('  uv run python scripts/evaluate_swebench.py', label, '--patch', patch_file)
    else:
        print('  uv run python scripts/evaluate.py --task', args.task,
              '--evaluation', args.task / 'public_tests', '--patch', patch_file)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
