"""Offline checks for image recipe integration and conda PATH configuration."""
from pathlib import Path
from unittest.mock import patch

from assignment.env import Environment
from agent_sandbox_runtime import DockerImage


def test_environment_delegates_to_standalone_backend():
    with patch("assignment.env.Sandbox") as mock:
        sb = mock.return_value
        sb.execute.return_value = {
            "returncode": 0, "output": "Linux\n6.1\n#1\nx86_64\n", "stdout": "", "stderr": "", "exception_info": "",
        }
        with Environment("python:3.12") as env:
            env.execute("echo hello", cwd="/tmp", env={"HELLO": "world"})
            assert mock.call_args.kwargs["image"] == "python:3.12"
            assert sb.execute.call_args.kwargs["cwd"] == "/tmp"
            assert sb.execute.call_args.kwargs["env"] == {"HELLO": "world"}
        sb.stop.assert_called_once()


def test_uses_docker_image_recipe():
    from assignment.utils.image import build_testbed_image
    from assignment.task import Task
    task = Task.load("tasks/chess-terminal-move")
    with patch("assignment.utils.image.verify_source"):
        recipe = build_testbed_image(task)
    assert isinstance(recipe, DockerImage)
    assert recipe.pins == task.pins
