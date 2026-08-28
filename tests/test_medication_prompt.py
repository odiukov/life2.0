"""Tests for medication prompt builder."""
import pytest

pytestmark = pytest.mark.asyncio

from agents.medication.app.prompt import build_medication_prompt


async def test_define_prompt_asks_for_strict_json():
    p = await build_medication_prompt("define_medication", {"message": "магний 200мг каждый вечер"})
    assert "JSON" in p
    assert "name" in p and "dose" in p and "schedule" in p
    assert "магний 200мг каждый вечер" in p


async def test_log_medication_prompt_asks_for_name_extraction():
    p = await build_medication_prompt("log_medication", {"message": "выпил магний"})
    assert "name" in p.lower()
    assert "выпил магний" in p


async def test_list_active_prompt_no_llm_needed_hint():
    p = await build_medication_prompt("list_active", {"message": ""})
    assert p  # non-empty


async def test_analyze_prompt_includes_window():
    p = await build_medication_prompt(
        "analyze_adherence", {"message": "last week", "window_days": 7}
    )
    assert "7" in p
