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
                 credential_env: dict[str, str] | None = None):
        if not re.fullmatch(r'1\.\d+\.\d+', version):
            raise ValueError('Pin an OpenCode v1 release like 1.19.2')
        if not model or '/' not in model or any(x.isspace() for x in model):
            raise ValueError('Model must be provider/model, e.g. openai/gpt-5-mini')
        if timeout <= 0:
            raise ValueError('Timeout must be positive')
        self.environment = environment
        self.model = model
        self.version = version
        self.timeout = timeout
        self.credential_env = dict(credential_env or {})
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

    def _git(self, *argv: str) -> dict:
        return _check(self.environment.execute(['git', *argv], shell=False,
                                               cwd=self.environment.cwd, timeout=45),
                      'git ' + argv[0])

    def _extract_patch(self) -> str:
        # Include untracked source files via intent-to-add; avoid accidental
        # capture of generated configs and test modifications.
        tracked = self._git('diff', '--name-only', '-z', 'HEAD', '--').get('stdout', '').split('\0')
        untracked = self._git('ls-files', '--others', '--exclude-standard', '-z', '--').get('stdout', '').split('\0')
        selected = sorted({p for p in tracked + untracked if safe_source_path(p)})
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
            [OPENCODE_BINARY, 'run', '--auto', '--agent', 'build',
             '--model', self.model, '--format', 'json', task_prompt],
            shell=False, cwd='/testbed', timeout=self.timeout,
            env=self.credential_env,
        )
        _check(result, 'OpenCode run')
        patch = self._extract_patch()
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
