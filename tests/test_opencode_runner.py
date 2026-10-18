"""Fast, offline unit coverage for the optional OpenCode backend."""

from __future__ import annotations

import pytest
import subprocess

from assignment.opencode_runner import (
    DEFAULT_OPENCODE_VERSION, OPENCODE_BINARY, OpenCodeRunner,
    credentials_from_host, redact_credentials, safe_source_path,
)


class StubEnvironment:
    cwd = '/testbed'

    def __init__(self, *, status='', agent_exit=0, dirty_files=None):
        self.calls = []
        self.status = status
        self.agent_exit = agent_exit
        self.dirty_files = dirty_files or ['src/fix.py', 'tests/test_fix.py']

    def execute(self, command, *, shell=False, cwd=None, env=None, timeout=None):
        self.calls.append((command, shell, cwd, env, timeout))
        stdout = ''
        code = 0
        if command[:2] == ['git', 'status']:
            stdout = self.status
        elif command[:3] == ['git', 'diff', '--name-only']:
            stdout = '\0'.join(self.dirty_files) + '\0'
        elif command[:3] == ['git', 'ls-files', '--others']:
            stdout = 'src/added.py\0AGENTS.md\0'
        elif command[:3] == ['git', 'diff', '--binary']:
            stdout = 'diff --git a/src/fix.py b/src/fix.py\n+fix\n'
        elif command[0] == OPENCODE_BINARY and 'run' in command:
            code = self.agent_exit
            stdout = '{"type":"step_finish"}\n'
        elif command[0] == OPENCODE_BINARY:
            stdout = DEFAULT_OPENCODE_VERSION + '\n'
        return {'returncode': code, 'stdout': stdout, 'stderr': '', 'output': stdout}


def test_path_filter_excludes_tests_and_agent_files():
    assert safe_source_path('src/assignment/fix.py')
    assert not safe_source_path('tests/test_bug.py')
    assert not safe_source_path('src/test_bug.py')
    assert not safe_source_path('.opencode/config.json')
    assert not safe_source_path('AGENTS.md')
    assert not safe_source_path('patch.txt')
    assert not safe_source_path('../escape.py')


def test_run_delegates_inside_sandbox_and_extracts_source_only():
    env = StubEnvironment()
    runner = OpenCodeRunner(env, model='openai/gpt-5-mini',
                            credential_env={'OPENAI_API_KEY': 'FAKE_UNIT_TEST_KEY'})
    result = runner.run('Fix the issue')
    assert result.patch.startswith('diff --git')
    install_cmd = next(c for c in env.calls if c[0][:2] == ['python', '-c'])
    assert install_cmd[3] is None
    agent_cmd = next(c for c in env.calls if c[0][0] == OPENCODE_BINARY and 'run' in c[0])
    assert agent_cmd[1] is False and agent_cmd[2] == '/testbed'
    assert agent_cmd[3] == {'OPENAI_API_KEY': 'FAKE_UNIT_TEST_KEY'}
    assert '--auto' in agent_cmd[0]
    add_cmd = next(c for c in env.calls if c[0][:3] == ['git', 'add', '-N'])
    assert 'src/added.py' in add_cmd[0]
    assert 'AGENTS.md' not in add_cmd[0]
    diff_cmd = next(c for c in env.calls if c[0][:3] == ['git', 'diff', '--binary'])
    assert 'tests/test_fix.py' not in diff_cmd[0]
    assert 'src/fix.py' in diff_cmd[0]


def test_dirty_baseline_fails_before_download():
    env = StubEnvironment(status=' M src/fix.py\n')
    with pytest.raises(RuntimeError, match='not clean'):
        OpenCodeRunner(env, model='openai/gpt-5-mini').run('Fix')
    assert not any(c[0][:2] == ['python', '-c'] for c in env.calls)


def test_nonzero_agent_exit_never_claims_patch():
    with pytest.raises(RuntimeError, match='OpenCode run failed'):
        OpenCodeRunner(StubEnvironment(agent_exit=1), model='openai/gpt-5-mini').run('Fix')


def test_validation_and_credentials_allowlist(monkeypatch):
    with pytest.raises(ValueError, match='Pin'):
        OpenCodeRunner(StubEnvironment(), model='openai/gpt-5-mini', version='latest')
    with pytest.raises(ValueError, match='provider/model'):
        OpenCodeRunner(StubEnvironment(), model='gpt-5-mini')
    with pytest.raises(ValueError, match='Unsupported'):
        OpenCodeRunner(StubEnvironment(), model='openai/gpt-5-mini',
                       credential_env={'AWS_SECRET_ACCESS_KEY': 'bad'})
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
    assert credentials_from_host().get('OPENAI_API_KEY') == 'test'
    assert 'AWS_SECRET_ACCESS_KEY' not in credentials_from_host()


def test_redaction_avoids_leaking_known_key_values():
    text = 'Agent said abcXYZ, another secret yy and abcXYZ again'
    assert redact_credentials(text, {'OPENAI_API_KEY': 'abcXYZ', 'OPENCODE_API_KEY': 'yy'}) == (
        'Agent said [REDACTED], another secret [REDACTED] and [REDACTED] again'
    )


def test_real_git_patch_filters_tests_and_includes_new_code(tmp_path):
    # Exercise the actual git plumbing without requiring Docker, network or API.
    repo = tmp_path / 'repo'
    repo.mkdir()

    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, text=True, capture_output=True, check=True)

    git('init', '-q')
    git('config', 'user.email', 'unit@example.com')
    git('config', 'user.name', 'Unit Tester')
    (repo / 'src').mkdir()
    (repo / 'src' / 'main.py').write_text('x = 0\n')
    (repo / 'tests').mkdir()
    (repo / 'tests' / 'test_main.py').write_text('assert False\n')
    git('add', '.')
    git('commit', '-q', '-m', 'baseline')
    (repo / 'src' / 'main.py').write_text('x = 1\n')
    (repo / 'src' / 'new_file.py').write_text('new = True\n')
    (repo / 'tests' / 'test_main.py').write_text('assert True\n')
    (repo / 'AGENTS.md').write_text('Do not include this\n')

    class LocalGitEnv:
        cwd = '/testbed'

        def execute(self, command, *, shell=False, cwd=None, env=None, timeout=None):
            assert cwd == '/testbed' and shell is False
            p = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
            return dict(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr,
                        output=p.stdout + p.stderr)

    patch = OpenCodeRunner(LocalGitEnv(), model='openai/gpt-5-mini')._extract_patch()
    assert 'src/main.py' in patch
    assert 'src/new_file.py' in patch
    assert 'tests/test_main.py' not in patch
    assert 'AGENTS.md' not in patch
    assert '+x = 1' in patch
    assert '+new = True' in patch
