import logging

from .db import list_user_credentials, update_token

logger = logging.getLogger(__name__)

_garmin_tokens: dict[str, str] = {}
_yazio_tokens: dict[str, dict] = {}


async def get_garmin_token(user_id: str) -> str | None:
    if user_id in _garmin_tokens:
        return _garmin_tokens[user_id]
    try:
        creds_list = await list_user_credentials("garmin")
        for uid, payload in creds_list:
            if uid == user_id:
                token = payload.get("garmin_token")
                if token:
                    _garmin_tokens[user_id] = token
                return token
    except Exception as e:
        logger.warning("Failed to read garmin token from DB for %s: %s", user_id, e)
    return None


async def save_garmin_token(user_id: str, token: str) -> None:
    _garmin_tokens[user_id] = token
    try:
        await update_token(user_id, "garmin", "garmin_token", token)
    except Exception as e:
        logger.warning("Failed to save garmin token to DB for %s: %s", user_id, e)


async def get_yazio_token(user_id: str) -> dict | None:
    if user_id in _yazio_tokens:
        return _yazio_tokens[user_id]
    try:
        creds_list = await list_user_credentials("yazio")
        for uid, payload in creds_list:
            if uid == user_id:
                token = payload.get("yazio_token")
                if token:
                    _yazio_tokens[user_id] = token
                return token
    except Exception as e:
        logger.warning("Failed to read yazio token from DB for %s: %s", user_id, e)
    return None


async def save_yazio_token(user_id: str, token: dict) -> None:
    _yazio_tokens[user_id] = token
    try:
        await update_token(user_id, "yazio", "yazio_token", token)
    except Exception as e:
        logger.warning("Failed to save yazio token to DB for %s: %s", user_id, e)
