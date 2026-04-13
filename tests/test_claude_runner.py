import pytest
from unittest.mock import patch, MagicMock
from shared.claude_runner import run_claude


def test_run_claude_returns_stdout():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Hello from Claude\n"
    mock_result.stderr = ""

    with patch("shared.claude_runner.shutil.which", return_value="/usr/bin/claude"):
        with patch("shared.claude_runner.subprocess.run", return_value=mock_result):
            result = run_claude("say hello")

    assert result == "Hello from Claude"


def test_run_claude_raises_on_nonzero_exit():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "error"

    with patch("shared.claude_runner.shutil.which", return_value="/usr/bin/claude"):
        with patch("shared.claude_runner.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="claude exited 1"):
                run_claude("bad prompt")


def test_run_claude_raises_when_not_found():
    with patch("shared.claude_runner.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="claude CLI not found"):
            run_claude("any prompt")
