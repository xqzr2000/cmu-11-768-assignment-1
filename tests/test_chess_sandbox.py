"""Actual chess testbed build, application port, API, and cleanup."""
import pytest
from agent_sandbox_runtime.process import docker_ready
from assignment.chess_sandbox import ChessSandbox, IllegalMove

pytestmark = pytest.mark.docker

@pytest.fixture(autouse=True)
def docker_available():
    ready, detail = docker_ready()
    if not ready:
        pytest.fail(f"Docker integration requires a running daemon: {detail}")


def test_chess_api_through_local_loopback():
    with ChessSandbox() as sandbox:
        assert sandbox.server_url.startswith("http://127.0.0.1:")
        state = sandbox.state()
        assert state["turn"] == "white" and state["history"] == []
        with pytest.raises(IllegalMove):
            sandbox.play("e2e5")
        assert sandbox.reset()["history"] == []
    assert not sandbox.is_alive()
