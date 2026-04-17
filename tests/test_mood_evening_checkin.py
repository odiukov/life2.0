import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_evening_checkin_registered_when_flag_on(monkeypatch):
    monkeypatch.setenv("MOOD_EVENING_CHECKIN", "true")
    monkeypatch.setenv("MOOD_EVENING_CHECKIN_TIME", "21:00")
    monkeypatch.setenv("MOOD_EVENING_CHECKIN_TZ", "Europe/Kyiv")

    fake_scheduler = MagicMock()
    with patch("sync_service.app.scheduler.AsyncIOScheduler", return_value=fake_scheduler):
        from sync_service.app.scheduler import start_scheduler
        start_scheduler()

    job_ids = [call.kwargs.get("id") for call in fake_scheduler.add_job.call_args_list]
    assert "mood_evening_checkin" in job_ids


def test_evening_checkin_absent_when_flag_off(monkeypatch):
    monkeypatch.delenv("MOOD_EVENING_CHECKIN", raising=False)

    fake_scheduler = MagicMock()
    with patch("sync_service.app.scheduler.AsyncIOScheduler", return_value=fake_scheduler):
        from sync_service.app.scheduler import start_scheduler
        start_scheduler()

    job_ids = [call.kwargs.get("id") for call in fake_scheduler.add_job.call_args_list]
    assert "mood_evening_checkin" not in job_ids


@pytest.mark.asyncio
async def test_send_checkin_prompt_posts_to_telegram():
    with patch("sync_service.app.scheduler.httpx.AsyncClient") as fake_client_cls:
        fake_client = AsyncMock()
        fake_client.__aenter__.return_value = fake_client
        fake_client.__aexit__.return_value = None
        fake_client.post = AsyncMock(return_value=MagicMock(raise_for_status=lambda: None))
        fake_client_cls.return_value = fake_client

        import sync_service.app.scheduler as sched
        import os
        os.environ["TELEGRAM_BOT_TOKEN"] = "tok"
        os.environ["TELEGRAM_CHAT_ID"] = "42"
        await sched._send_mood_checkin()

    fake_client.post.assert_awaited()
    call = fake_client.post.call_args
    assert "sendMessage" in call.args[0]
    assert call.kwargs["json"]["chat_id"] == "42"
