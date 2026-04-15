"""Unit tests for ChatClaudeCLI — mocks the subprocess, no real CLI calls."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult

from shared.chat_claude_cli import ChatClaudeCLI


@pytest.fixture(autouse=True)
def _fake_claude_on_path(monkeypatch, tmp_path):
    # Simulate `claude` being on PATH by stubbing shutil.which used inside the adapter.
    monkeypatch.setattr("shared.chat_claude_cli.shutil.which", lambda name: "/usr/bin/claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat-test-token")


def _fake_process(stdout: bytes = b"pong", stderr: bytes = b"", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=None)
    return proc


@pytest.mark.asyncio
async def test_agenerate_spawns_expected_cmd():
    llm = ChatClaudeCLI(model="claude-sonnet-4-6")
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_process())) as spawn:
        await llm._agenerate([HumanMessage("hello")])
    args, kwargs = spawn.call_args
    assert args[0] == "/usr/bin/claude"
    assert "--print" in args
    assert "--bare" in args
    assert "--model" in args and args[args.index("--model") + 1] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_system_message_is_prepended_to_prompt():
    llm = ChatClaudeCLI()
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_process())) as spawn:
        await llm._agenerate([SystemMessage("you are a bot"), HumanMessage("hi")])
    args, _ = spawn.call_args
    prompt = args[-1]
    assert prompt.startswith("you are a bot")
    assert "hi" in prompt


@pytest.mark.asyncio
async def test_returns_chatresult_with_aimessage():
    llm = ChatClaudeCLI()
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_process(b"pong"))):
        result = await llm._agenerate([HumanMessage("ping")])
    assert isinstance(result, ChatResult)
    assert len(result.generations) == 1
    msg = result.generations[0].message
    assert isinstance(msg, AIMessage)
    assert msg.content == "pong"


@pytest.mark.asyncio
async def test_subprocess_error_propagates():
    llm = ChatClaudeCLI()
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_process(b"", b"boom", returncode=2))):
        with pytest.raises(RuntimeError, match="boom"):
            await llm._agenerate([HumanMessage("x")])


@pytest.mark.asyncio
async def test_subprocess_timeout():
    llm = ChatClaudeCLI(timeout_seconds=0)
    proc = AsyncMock()

    async def _never(*_a, **_kw):
        import asyncio
        await asyncio.sleep(10)

    proc.communicate = _never
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=None)
    proc.returncode = None
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=proc)):
        with pytest.raises(TimeoutError):
            await llm._agenerate([HumanMessage("x")])


@pytest.mark.asyncio
async def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    llm = ChatClaudeCLI()
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        await llm._agenerate([HumanMessage("x")])


def test_llm_type():
    assert ChatClaudeCLI()._llm_type == "claude-cli"


def test_bind_tools_raises_clear_error():
    llm = ChatClaudeCLI()
    with pytest.raises(NotImplementedError, match="does not support tool calling"):
        llm.bind_tools([{"name": "dummy"}])
