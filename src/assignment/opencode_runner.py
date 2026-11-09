"""Optional OpenCode coding backend, running entirely inside a task Docker sandbox.

This module intentionally does not modify the assignment's CodeAgent or grading
protocol. OpenCode v1 is installed from a versioned GitHub release at runtime;
model credentials are passed only to the single agent process, never to builds.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol

# Install to ephemeral storage, never the task's /testbed working tree.
OPENCODE_BINARY = "/tmp/assignment-opencode/bin/opencode"
DEFAULT_OPENCODE_VERSION = "1.19.2"  # v1 CLI, pinned for repeatable tests.
DEFAULT_TIMEOUT = 1200
ALLOWED_CREDENTIALS = (
    "OPENAI_API_KEY", "OPENCODE_API_KEY", "ANTHROPIC_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY", "GEMINI_API_KEY",
)
DEFAULT_FREE_MODEL = "opencode/deepseek-v4.1-flash-free"
# OpenCode's own free tier: `opencode/<id>-free`. Nothing here needs a key.
FREE_MODEL_PATTERN = re.compile(r"opencode/[a-z0-9][a-z0-9.\-]*-free")
# Names that look like a credential. Free-only runs refuse to start when any
# such variable is visible inside the container.
CREDENTIAL_NAME_PATTERN = re.compile(
    r"(API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|ACCESS_KEY|PRIVATE_KEY)", re.I
)
PROBE_PROMPT = "Reply with exactly READY. Do not inspect or edit files."
# Without these, OpenCode prints provider errors (e.g. "Free usage limit
# reached") nowhere and then hangs until the timeout, so a quota failure looks
# like a silent timeout. WARN keeps ERROR lines without INFO noise; the JSON
# event parser skips the non-JSON log lines.
LOG_FLAGS = ('--print-logs', '--log-level', 'WARN')
_QUOTA_MARKERS = ("free usage limit", "usage limit reached", "rate limit", "quota")


def is_free_opencode_model(model: str) -> bool:
    """True only for OpenCode's free-tier models, which need no API key."""
    return bool(FREE_MODEL_PATTERN.fullmatch(model or ""))


def credential_like_names(names) -> list[str]:
    return sorted({n for n in names if n and CREDENTIAL_NAME_PATTERN.search(n)})


def classify_run_output(output: str, returncode: int | None) -> str:
    """Name what happened in an OpenCode process, for comparison records.

    ``ok`` only means the process exited 0; whether a patch exists and passes
    the tests is decided separately by the evaluator.
    """
    text = (output or "").lower()
    if any(marker in text for marker in _QUOTA_MARKERS):
        return "quota_limited"
    if returncode == 124:
        return "timeout"
    if returncode == 0:
        return "ok"
    return "error"


class OpenCodeRunError(RuntimeError):
    """The OpenCode process failed; keeps its output so the failure is auditable."""

    def __init__(self, message: str, *, output: str = "", returncode: int | None = None):
        super().__init__(message)
        self.output = output
        self.returncode = returncode
        self.status = classify_run_output(output, returncode)

# Executed by the testbed's own Python interpreter. Avoids assuming curl,
# npm, sudo or a writable system Python in arbitrary SWE-bench images.
_INSTALL_SCRIPT = r'''
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

version = sys.argv[1]
arch = {'x86_64': 'x64', 'aarch64': 'arm64'}.get(platform.machine())
if sys.platform != 'linux' or arch is None:
    raise SystemExit('OpenCode sandbox runner supports Linux x86_64 and aarch64')

suffix = ''
if os.path.exists('/etc/alpine-release'):
    suffix = '-musl'
else:
    try:
        p = subprocess.run(['ldd', '--version'], capture_output=True, text=True)
        if 'musl' in (p.stdout + p.stderr).lower():
            suffix = '-musl'
    except OSError:
        pass
if arch == 'x64' and suffix != '-musl':
    try:
        with open('/proc/cpuinfo') as f:
            if 'avx2' not in f.read().lower():
                suffix = '-baseline'
    except OSError:
        suffix = '-baseline'

asset = 'opencode-linux-' + arch + suffix + '.tar.gz'
url = ('https://github.com/anomalyco/opencode/releases/download/v'
       + version + '/' + asset)
path = '/tmp/assignment-opencode/bin/opencode'
os.makedirs(os.path.dirname(path), exist_ok=True)
with tempfile.TemporaryFile() as downloaded:
    with urllib.request.urlopen(url, timeout=120) as response:
        shutil.copyfileobj(response, downloaded)
    downloaded.seek(0)
    with tarfile.open(fileobj=downloaded, mode='r:gz') as archive:
        binary = next((m for m in archive.getmembers()
                       if m.isfile() and os.path.basename(m.name) == 'opencode'), None)
        if binary is None:
            raise SystemExit('Release archive has no opencode executable')
        src = archive.extractfile(binary)
        if src is None:
            raise SystemExit('Could not read opencode executable from release')
        with src, open(path, 'wb') as dest:
            shutil.copyfileobj(src, dest)
os.chmod(path, 0o755)
print('Installed OpenCode v' + version + ' to ' + path)
'''


class CommandEnvironment(Protocol):
    cwd: str

    def execute(self, command: list[str], *, shell: bool = False, cwd: str | None = None,
                env: dict[str, str] | None = None, timeout: float | None = None) -> dict: ...


@dataclass(frozen=True)
class OpenCodeRun:
    patch: str
    output: str
    model: str
    version: str
    command_returncode: int


def safe_source_path(path: str) -> bool:
    """Keep candidate diffs free of tests, hidden agent data and harness output.

    This is intentionally conservative: a missing patch is better than a
    misleading patch containing changes to the graded tests.
    """
    if not path or path.startswith('/') or '\\' in path:
        return False
    parts = path.split('/')
    if any(p in {'', '.', '..', '.git', '.opencode', '__pycache__', 'tests', 'test',
                 'testing', 'fixtures', '.github'} for p in parts):
        return False
    name = parts[-1]
    if name in {'patch.txt', 'AGENTS.md', 'opencode.json', 'opencode.jsonc',
                'conftest.py', 'pytest.ini', 'tox.ini'}:
        return False
    if name.startswith('test_') or name.endswith(('_test.py', '.pyc', '.patch', '.diff')):
        return False
    if name.startswith('.') or name.endswith(('.log', '.jsonl')):
        return False
    return True


def _check(result: dict, context: str) -> dict:
    if result.get('returncode') != 0:
        msg = (result.get('stderr') or result.get('output') or '')[-3000:]
        raise RuntimeError(f'{context} failed (exit {result.get("returncode")}): {msg}')
    return result


class OpenCodeRunner:
    def __init__(self, environment: CommandEnvironment, *, model: str,
                 version: str = DEFAULT_OPENCODE_VERSION,
                 timeout: int = DEFAULT_TIMEOUT,
                 credential_env: dict[str, str] | None = None,
                 allowed_paths: tuple[str, ...] | None = None,
                 free_only: bool = False):
        if not re.fullmatch(r'1\.\d+\.\d+', version):
            raise ValueError('Pin an OpenCode v1 release like 1.19.2')
        if not model or '/' not in model or any(x.isspace() for x in model):
            raise ValueError('Model must be provider/model, e.g. openai/gpt-5-mini')
        if timeout <= 0:
            raise ValueError('Timeout must be positive')
        if free_only and not is_free_opencode_model(model):
            raise ValueError(
                f'free_only allows only OpenCode free models (opencode/<id>-free), not {model!r}'
            )
        if free_only and credential_env:
            raise ValueError('free_only runs must not receive any credentials')
        self.free_only = free_only
        self.environment = environment
        self.model = model
        self.version = version
        self.timeout = timeout
        self.credential_env = dict(credential_env or {})
        self.allowed_paths = (
            None if allowed_paths is None
            else frozenset(allowed_paths)
        )
        if self.allowed_paths is not None:
            if not self.allowed_paths or any(
                not safe_source_path(p) for p in self.allowed_paths
            ):
                raise ValueError("Invalid allowed_paths")
        disallowed = set(self.credential_env) - set(ALLOWED_CREDENTIALS)
        if disallowed:
            raise ValueError('Unsupported credential environment variable(s): ' + ', '.join(sorted(disallowed)))

    def install(self) -> str:
        env = self.environment
        result = env.execute(['python', '-c', _INSTALL_SCRIPT, self.version],
                             shell=False, cwd='/tmp', timeout=360)
        _check(result, 'OpenCode install')
        result = env.execute([OPENCODE_BINARY, '--version'], shell=False,
                             cwd='/tmp', timeout=30)
        return _check(result, 'OpenCode version check').get('output', '').strip()

    def assert_no_credentials_in_container(self) -> None:
        """Free-only guard: fail if anything credential-like is visible in the sandbox.

        Checks the environment the agent command will actually see (container
        env plus what this runner passes), not just what the host intended.
        """
        result = _check(self.environment.execute(
            ['env'], shell=False, cwd='/tmp', env=self.credential_env, timeout=30),
            'Listing sandbox environment')
        names = [line.split('=', 1)[0] for line in result.get('stdout', '').splitlines() if '=' in line]
        leaked = credential_like_names(names)
        if leaked:
            raise RuntimeError(
                'Free-only run refused: credential-like variables visible in the sandbox: '
                + ', '.join(leaked)
            )

    def probe(self, timeout: int = 120) -> dict:
        """One trivial request to confirm the model actually serves inference.

        A model appearing in OpenCode's catalog does not mean quota remains.
        """
        self.install()
        if self.free_only:
            self.assert_no_credentials_in_container()
        result = self.environment.execute(
            [OPENCODE_BINARY, 'run', *LOG_FLAGS, '--model', self.model, '--format', 'json', PROBE_PROMPT],
            shell=False, cwd='/tmp', timeout=timeout, env=self.credential_env,
        )
        output = result.get('output', '')
        status = classify_run_output(output, result.get('returncode'))
        if status == 'ok' and 'READY' not in output:
            status = 'no_answer'
        return {'status': status, 'returncode': result.get('returncode'), 'output': output}

    def _git(self, *argv: str) -> dict:
        return _check(self.environment.execute(['git', *argv], shell=False,
                                               cwd=self.environment.cwd, timeout=45),
                      'git ' + argv[0])

    def _extract_patch(self) -> str:
        # Include untracked source files via intent-to-add; avoid accidental
        # capture of generated configs and test modifications.
        tracked = self._git('diff', '--name-only', '--no-renames', '-z', 'HEAD', '--').get('stdout', '').split('\0')
        untracked = self._git('ls-files', '--others', '--exclude-standard', '-z', '--').get('stdout', '').split('\0')
        changed = {p for p in tracked + untracked if p}
        if self.allowed_paths is not None:
            forbidden = sorted(changed - self.allowed_paths)
            if forbidden:
                raise RuntimeError(
                    "OpenCode changed files outside allowlist: "
                    + ", ".join(forbidden)
                )
        selected = sorted(
            p for p in changed
            if safe_source_path(p)
            and (self.allowed_paths is None or p in self.allowed_paths)
        )
        if not selected:
            raise RuntimeError('OpenCode did not produce any allowable source changes')
        new_files = sorted({p for p in untracked if safe_source_path(p)})
        if new_files:
            self._git('add', '-N', '--', *new_files)
        patch = self._git('diff', '--binary', '--no-ext-diff', 'HEAD', '--', *selected).get('stdout', '')
        if not patch.strip():
            raise RuntimeError('Source diff is empty after filtering out test and agent files')
        return patch

    def run(self, issue: str) -> OpenCodeRun:
        if not issue.strip():
            raise ValueError('Issue text must not be empty')
        if self.environment.cwd != '/testbed':
            raise ValueError('OpenCode task must operate in /testbed')
        _check(self.environment.execute(['git', 'rev-parse', '--is-inside-work-tree'],
                                        cwd='/testbed', shell=False, timeout=30),
               'Checking testbed git repository')
        status = self._git('status', '--porcelain', '--untracked-files=all').get('stdout', '')
        if status.strip():
            raise RuntimeError('Task testbed is not clean; use a new disposable sandbox')
        self.install()
        if self.free_only:
            self.assert_no_credentials_in_container()
        task_prompt = (
            'Resolve this software engineering issue in the repository at /testbed.\n'
            'Read the code and reproduce the bug, make a minimal source-code fix, '
            'and run relevant existing tests. Do NOT edit tests, fixtures, '
            'AGENTS.md or OpenCode configuration files. Do NOT git commit. '
            'Do NOT generate patch.txt; the outer controller will extract the diff.\n\n'
            '<issue>\n' + issue.strip() + '\n</issue>'
        )
        # Only the agent command sees credentials, not the image build or other
        # commands (installation, git, tests). This nevertheless grants the
        # agent access to credentials and should only be used with trusted tasks.
        result = self.environment.execute(
            [OPENCODE_BINARY, 'run', *LOG_FLAGS, '--auto', '--agent', 'build',
             '--model', self.model, '--format', 'json', task_prompt],
            shell=False, cwd='/testbed', timeout=self.timeout,
            env=self.credential_env,
        )
        if result.get('returncode') != 0:
            output = result.get('output', '')
            raise OpenCodeRunError(
                f'OpenCode run failed (exit {result.get("returncode")}): '
                + (result.get('stderr') or output)[-3000:],
                output=output, returncode=result.get('returncode'),
            )
        try:
            patch = self._extract_patch()
        except RuntimeError as exc:
            error = OpenCodeRunError(str(exc), output=result.get('output', ''),
                                     returncode=result.get('returncode'))
            if error.status == 'ok':
                error.status = 'no_patch'
            raise error from exc
        return OpenCodeRun(patch=patch, output=result.get('output', ''),
                           model=self.model, version=self.version,
                           command_returncode=result['returncode'])


def credentials_from_host() -> dict[str, str]:
    """Deliberate allowlist: no wholesale copying of Codespaces secrets."""
    return {key: os.environ[key] for key in ALLOWED_CREDENTIALS if os.environ.get(key)}


def redact_credentials(output: str, credential_env: dict[str, str]) -> str:
    """Best-effort protection against an agent echoing a supplied API key.

    JSON events may still contain private source and should be kept local.
    """
    for secret in sorted(set(credential_env.values()), key=len, reverse=True):
        if secret:
            output = output.replace(secret, '[REDACTED]')
    return output
