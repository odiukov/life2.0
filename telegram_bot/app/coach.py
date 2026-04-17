"""Bounded coach-session loop — ephemeral in-memory state, Groq-only LLM."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class CoachAlreadyActive(Exception):
    pass


class CoachUnavailable(Exception):
    pass


@dataclass
class CoachSession:
    chat_id: int
    started_at: datetime
    last_turn_at: datetime
    turns: list[dict] = field(default_factory=list)
    turn_count: int = 0


LlmCall = Callable[[list[dict]], Awaitable[str]]
LogMoodCall = Callable[[dict], Awaitable[None]]


_SYSTEM_PROMPT = (
    "You are an empathetic coach. Ask one short open question per turn. "
    "Do NOT give advice, do NOT diagnose, do NOT repeat the user's words back. "
    "Keep each reply under 3 sentences."
)

_FINAL_EXTRACT_PROMPT = (
    "The coach session is complete. Review the transcript and emit STRICT JSON only "
    "with keys: mood_score (int 1-10 or null), energy (int 1-10 or null), "
    "stress (int 1-10 or null), valence ('pos'|'neu'|'neg' or null), "
    "tags (lowercase strings, max 6), summary (3-line plain-text recap)."
)


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _parse_final_json(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(text)
        if not m:
            return None
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


class CoachLoop:
    def __init__(self, *, llm_call: LlmCall, log_mood_call: LogMoodCall, max_turns: int = 6):
        self._llm = llm_call
        self._log = log_mood_call
        self._max_turns = max_turns
        self._sessions: dict[int, CoachSession] = {}

    def has_session(self, chat_id: int) -> bool:
        return chat_id in self._sessions

    def session(self, chat_id: int) -> CoachSession:
        return self._sessions[chat_id]

    async def start(self, *, chat_id: int, recent_context: str) -> str:
        if chat_id in self._sessions:
            raise CoachAlreadyActive(chat_id)
        now = datetime.now(timezone.utc)
        sess = CoachSession(chat_id=chat_id, started_at=now, last_turn_at=now)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT + f"\nContext: {recent_context or '(none)'}"},
            {"role": "user", "content": "Start the session."},
        ]
        try:
            reply = await self._llm(messages)
        except Exception as e:
            logger.warning("coach llm start failed: %s", e)
            raise CoachUnavailable(str(e)) from e
        sess.turns.append({"role": "assistant", "content": reply})
        sess.turn_count = 1
        self._sessions[chat_id] = sess
        return reply

    async def continue_(self, *, chat_id: int, user_text: str) -> str:
        sess = self._sessions.get(chat_id)
        if sess is None:
            return "No active coach session. Use /coach to start."
        sess.turns.append({"role": "user", "content": user_text})
        sess.last_turn_at = datetime.now(timezone.utc)
        if sess.turn_count >= self._max_turns:
            return await self.stop(chat_id=chat_id)
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}] + [
            {"role": t["role"], "content": t["content"]} for t in sess.turns
        ]
        try:
            reply = await self._llm(messages)
        except Exception as e:
            logger.warning("coach llm continue failed: %s", e)
            self._sessions.pop(chat_id, None)
            raise CoachUnavailable(str(e)) from e
        sess.turns.append({"role": "assistant", "content": reply})
        sess.turn_count += 1
        return reply

    async def stop(self, *, chat_id: int) -> str:
        sess = self._sessions.pop(chat_id, None)
        if sess is None:
            return "No active coach session."
        transcript = "\n".join(
            ("User: " if t["role"] == "user" else "Coach: ") + t["content"]
            for t in sess.turns
        )
        messages = [
            {"role": "system", "content": _FINAL_EXTRACT_PROMPT},
            {"role": "user", "content": transcript},
        ]
        try:
            raw = await self._llm(messages)
        except Exception as e:
            logger.warning("coach llm finalize failed: %s", e)
            return "Coach session closed, but summary generation failed."
        parsed = _parse_final_json(raw)
        summary = (parsed or {}).get("summary") or "Coach session closed."
        try:
            await self._log({
                "mood_score": (parsed or {}).get("mood_score"),
                "energy": (parsed or {}).get("energy"),
                "stress": (parsed or {}).get("stress"),
                "valence": (parsed or {}).get("valence"),
                "tags": (parsed or {}).get("tags") or [],
                "raw_text": transcript,
                "source_skill": "coach_session",
            })
        except Exception as e:
            logger.warning("coach log_mood write failed: %s", e)
        return summary


def default_llm_call():
    """Build the Groq-based call coroutine bound to the telegram process lifecycle."""
    from langchain_groq import ChatGroq
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    provider = os.environ.get("MOOD_COACH_PROVIDER", "groq")
    if provider != "groq":
        raise RuntimeError(
            f"MOOD_COACH_PROVIDER={provider!r} is not supported. This implementation is "
            "Groq-only by design (see spec). Set MOOD_COACH_PROVIDER=groq."
        )
    model = os.environ.get("MOOD_COACH_MODEL", "llama-3.3-70b-versatile")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    llm = ChatGroq(model=model, api_key=api_key, temperature=0.6)

    async def _call(messages: list[dict]) -> str:
        lc_messages = []
        for m in messages:
            role = m["role"]
            content = m["content"]
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))
        result = await llm.ainvoke(lc_messages)
        return result.content if isinstance(result.content, str) else str(result.content)

    return _call


def default_log_mood_call():
    """Post to the orchestrator so the mood agent records the session aggregate."""
    import httpx

    orchestrator_url = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")

    async def _call(entry: dict) -> None:
        # Use the /chat/stream so routing goes through the ReAct graph and the
        # mood agent receives source_skill='coach_session' in params.
        message = f"mood log session summary: {entry.get('raw_text', '')[:2000]}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{orchestrator_url}/chat/stream",
                json={"messages": [{"role": "user", "content": message}]},
            )
            resp.raise_for_status()

    return _call
