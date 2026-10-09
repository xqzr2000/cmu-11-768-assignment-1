"""Docker integration checks, skipped in ordinary offline unit test runs."""
import pytest
from agent_sandbox_runtime.process import docker_ready
from assignment.env import Environment

pytestmark = pytest.mark.docker

@pytest.fixture(autouse=True)
def docker_available():
    ready, detail = docker_ready()
    if not ready:
        pytest.fail(f"Docker integration requires a running daemon: {detail}")


def test_shell_argv_failure_and_cleanup():
    with Environment(deployment_timeout=120) as env:
        assert env.is_alive()
        assert env.execute("echo 'hello, world'")["output"] == "hello, world\n"
        assert env.execute(["echo", "hello, world"], shell=False)["returncode"] == 0
        result = env.execute("python -c 'raise RuntimeError(\"test exception\")'")
        assert result["returncode"] != 0 and "test exception" in result["output"]
    assert not env.is_alive()
