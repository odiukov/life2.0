import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_start_session_creates_record_and_posts_opener():
    from telegram_bot.app.coach import CoachLoop

    fake_llm = AsyncMock(return_value="what's on your mind?")
    loop = CoachLoop(llm_call=fake_llm, log_mood_call=AsyncMock(), max_turns=6)
    reply = await loop.start(chat_id=42, recent_context="recent mood: 6/10")
    assert reply == "what's on your mind?"
    assert loop.has_session(42)
    assert loop.session(42).turn_count == 1


@pytest.mark.asyncio
async def test_subsequent_turns_append_and_call_llm():
    from telegram_bot.app.coach import CoachLoop

    replies = ["how are you feeling?", "tell me more"]
    fake_llm = AsyncMock(side_effect=replies)
    loop = CoachLoop(llm_call=fake_llm, log_mood_call=AsyncMock(), max_turns=6)
    await loop.start(chat_id=42, recent_context="")
    r = await loop.continue_(chat_id=42, user_text="tired today")
    assert r == "tell me more"
    assert loop.session(42).turn_count == 2
    # turns: [assistant opener, user msg, assistant reply] after 1 continue_
    assert loop.session(42).turns[-1]["role"] == "assistant"
    assert loop.session(42).turns[-1]["content"] == "tell me more"
    assert loop.session(42).turns[-2]["role"] == "user"
    assert loop.session(42).turns[-2]["content"] == "tired today"


@pytest.mark.asyncio
async def test_session_finalizes_at_max_turns():
    from telegram_bot.app.coach import CoachLoop

    llm_replies = [f"reply {i}" for i in range(6)] + ['{"mood_score":5,"energy":4,"stress":7,"valence":"neg","tags":["tired"],"summary":"rough day"}']
    fake_llm = AsyncMock(side_effect=llm_replies)
    log_mock = AsyncMock()
    loop = CoachLoop(llm_call=fake_llm, log_mood_call=log_mock, max_turns=6)
    await loop.start(chat_id=42, recent_context="")
    for i in range(5):
        await loop.continue_(chat_id=42, user_text=f"msg {i}")

    # 1 opener + 5 continues = 6 assistant turns = max_turns reached. Next input must finalize.
    final = await loop.continue_(chat_id=42, user_text="one more thing")
    assert "rough day" in final or "summary" in final.lower() or "closed" in final.lower()
    assert not loop.has_session(42)
    log_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_finalizes_and_cleans_up():
    from telegram_bot.app.coach import CoachLoop

    llm_replies = ["opener", '{"mood_score":6,"energy":5,"stress":5,"valence":"neu","tags":["calm"],"summary":"okay"}']
    fake_llm = AsyncMock(side_effect=llm_replies)
    log_mock = AsyncMock()
    loop = CoachLoop(llm_call=fake_llm, log_mood_call=log_mock, max_turns=6)
    await loop.start(chat_id=42, recent_context="")
    final = await loop.stop(chat_id=42)
    assert "okay" in final or "summary" in final.lower() or "closed" in final.lower()
    assert not loop.has_session(42)
    log_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_double_start_rejected():
    from telegram_bot.app.coach import CoachLoop, CoachAlreadyActive

    fake_llm = AsyncMock(return_value="opener")
    loop = CoachLoop(llm_call=fake_llm, log_mood_call=AsyncMock(), max_turns=6)
    await loop.start(chat_id=42, recent_context="")
    with pytest.raises(CoachAlreadyActive):
        await loop.start(chat_id=42, recent_context="")


@pytest.mark.asyncio
async def test_llm_error_reports_unavailable_and_cleans_up():
    from telegram_bot.app.coach import CoachLoop, CoachUnavailable

    fake_llm = AsyncMock(side_effect=RuntimeError("groq 503"))
    loop = CoachLoop(llm_call=fake_llm, log_mood_call=AsyncMock(), max_turns=6)
    with pytest.raises(CoachUnavailable):
        await loop.start(chat_id=42, recent_context="")
    assert not loop.has_session(42)
