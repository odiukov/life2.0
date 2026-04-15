"""ChatClaudeCLI — a BaseChatModel adapter around the `claude` CLI subprocess.

Known limitations (documented here, not bugs):
- No streaming (the CLI's --print mode emits the full reply at once).
- No tool calling.
- No structured output.
- Requires ANTHROPIC_API_KEY in env (OAuth token from macOS Keychain via
  scripts/export-auth.sh). Token expires ~every 8h.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any, List, Optional

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ChatClaudeCLI(BaseChatModel):
    """LangChain chat model that shells out to the `claude` CLI.

    Uses `claude --print --bare --model {model} {prompt}` with
    ANTHROPIC_API_KEY (OAuth token) in the child process env. Messages are
    flattened into a single prompt (system first, then the rest in order)
    because --print takes one positional arg and has no role separation.
    """

    model: str = "claude-sonnet-4-6"
    timeout_seconds: int = 120

    @property
    def _llm_type(self) -> str:
        return "claude-cli"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model}

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return asyncio.run(self._agenerate(messages, stop, None, **kwargs))

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        token = os.environ.get("ANTHROPIC_API_KEY", "")
        if not token:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Run scripts/export-auth.sh to export "
                "the OAuth token from Keychain before starting containers."
            )
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError("claude CLI not found in PATH")

        prompt = self._flatten_messages(messages)

        cmd: list[str] = [claude_bin, "--print", "--bare", "--model", self.model, prompt]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ANTHROPIC_API_KEY": token},
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError as e:
            await proc.kill()
            raise TimeoutError(
                f"claude CLI timed out after {self.timeout_seconds}s"
            ) from e

        if proc.returncode != 0:
            err = (stderr or b"").decode(errors="replace")[:500]
            raise RuntimeError(f"claude exited {proc.returncode}: {err}")

        text = (stdout or b"").decode(errors="replace").strip()
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    @staticmethod
    def _flatten_messages(messages: List[BaseMessage]) -> str:
        """Join messages (system first, then rest in order) into one prompt string."""
        system_parts: list[str] = []
        other_parts: list[str] = []
        for m in messages:
            if isinstance(m, SystemMessage):
                system_parts.append(str(m.content))
            else:
                other_parts.append(str(m.content))
        return "\n\n".join(system_parts + other_parts).strip()
