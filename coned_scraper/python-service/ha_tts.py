"""
Send TTS via Home Assistant REST API (addon with homeassistant_api).
Waits for media player idle when configured.
"""
import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

HA_BASE = "http://supervisor/core"
IDLE_STATES = ("idle", "unknown", "unavailable")
MAX_WAIT_SECONDS = 300
POLL_INTERVAL = 2


async def _ha_request(
    method: str,
    path: str,
    json_body: Optional[dict] = None,
) -> tuple[int, Optional[dict]]:
    """Call Home Assistant REST API. Returns (status_code, json_response)."""
    import aiohttp
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        logger.warning("SUPERVISOR_TOKEN not set — not running as HA addon")
        return 401, None
    url = f"{HA_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            kwargs = {"headers": headers}
            if json_body is not None:
                kwargs["json"] = json_body
            async with session.request(method, url, **kwargs) as resp:
                data = None
                if resp.content_type and "json" in resp.content_type:
                    try:
                        data = await resp.json()
                    except Exception:
                        pass
                return resp.status, data
    except Exception as e:
        logger.error(f"HA request failed: {e}")
        return 500, None


async def _get_media_player_state(media_player: str) -> Optional[str]:
    """Get current state of media player."""
    status, data = await _ha_request("GET", f"/api/states/{media_player}")
    if status != 200 or not data:
        return None
    return data.get("state")


async def _wait_for_idle(media_player: str) -> bool:
    """Wait until media player is idle. Returns True if idle reached."""
    elapsed = 0
    while elapsed < MAX_WAIT_SECONDS:
        state = await _get_media_player_state(media_player)
        if state in IDLE_STATES:
            return True
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        logger.debug(f"Media player {media_player} state={state}, waiting...")
    logger.warning("Timeout waiting for media player idle")
    return False


async def send_tts(
    message: str,
    media_player: str,
    volume: float = 0.7,
    wait_for_idle: bool = True,
    tts_service: str = "tts.google_translate_say",
) -> tuple[bool, str]:
    """
    Send TTS via Home Assistant. Returns (success, error_message).
    Uses direct HA REST API when running as addon with homeassistant_api.
    
    Supports both new (tts.speak) and legacy (tts.<service>_say) formats:
    - New format (HA 2024+): tts.speak with target entity_id
    - Legacy format: tts.google_translate_say, etc.
    """
    if not message or not media_player:
        return False, "Message and media player required"
    media_player = media_player.strip()

    if wait_for_idle:
        idle = await _wait_for_idle(media_player)
        if not idle:
            return False, "Media player did not become idle in time"

    # Set volume first
    status, _ = await _ha_request(
        "POST",
        "/api/services/media_player/volume_set",
        {"entity_id": media_player, "volume_level": max(0.0, min(1.0, float(volume)))},
    )
    if status not in (200, 201):
        logger.warning(f"Volume set returned {status}, continuing with TTS")

    # Try the new tts.speak format first (HA 2024+)
    # tts.speak requires: entity_id (tts entity), media_player_entity_id, message
    if tts_service.startswith("tts.") and not tts_service.endswith("_say"):
        # New format: tts_service is the TTS entity (e.g., tts.google_en_com)
        status, data = await _ha_request(
            "POST",
            "/api/services/tts/speak",
            {
                "entity_id": tts_service,
                "media_player_entity_id": media_player,
                "message": message,
            },
        )
        if status in (200, 201):
            logger.info(f"TTS sent to {media_player} via tts.speak")
            return True, ""
        logger.warning(f"tts.speak returned {status}, trying legacy format...")
    
    # Try legacy format (tts.google_translate_say, tts.cloud_say, etc.)
    domain, service = tts_service.split(".", 1) if "." in tts_service else ("tts", "google_translate_say")
    
    status, data = await _ha_request(
        "POST",
        f"/api/services/{domain}/{service}",
        {"entity_id": media_player, "message": message},
    )
    if status in (200, 201):
        logger.info(f"TTS sent to {media_player} via {domain}/{service}")
        return True, ""
    
    # If legacy format also failed, try with media_player_entity_id (some TTS services use this)
    status, data = await _ha_request(
        "POST",
        f"/api/services/{domain}/{service}",
        {"media_player_entity_id": media_player, "message": message},
    )
    if status in (200, 201):
        logger.info(f"TTS sent to {media_player} via {domain}/{service} (media_player_entity_id)")
        return True, ""
    
    error_msg = f"TTS service returned {status}"
    if data and isinstance(data, dict) and data.get("message"):
        error_msg = f"{error_msg}: {data.get('message')}"
    
    return False, error_msg
