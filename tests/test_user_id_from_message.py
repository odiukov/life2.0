"""Tests for shared.current_user.user_id_from_message — strict mode."""
from __future__ import annotations

from uuid import UUID
from unittest.mock import MagicMock

import pytest

from shared.current_user import user_id_from_message


@pytest.mark.asyncio
async def test_reads_user_id_from_metadata():
    msg = MagicMock()
    msg.metadata = {"user_id": "11111111-1111-1111-1111-111111111111"}
    got = await user_id_from_message(msg)
    assert got == UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.asyncio
async def test_raises_when_metadata_none():
    msg = MagicMock()
    msg.metadata = None
    with pytest.raises(ValueError, match="missing user_id"):
        await user_id_from_message(msg)


@pytest.mark.asyncio
async def test_raises_when_user_id_absent():
    msg = MagicMock()
    msg.metadata = {"skillId": "log_sleep"}
    with pytest.raises(ValueError, match="missing user_id"):
        await user_id_from_message(msg)


@pytest.mark.asyncio
async def test_raises_when_user_id_malformed():
    msg = MagicMock()
    msg.metadata = {"user_id": "not-a-uuid"}
    with pytest.raises(ValueError, match="malformed user_id"):
        await user_id_from_message(msg)
