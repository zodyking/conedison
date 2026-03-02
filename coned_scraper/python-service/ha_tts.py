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
    language: str = "",
    cache: bool = False,
) -> tuple[bool, str]:
    """
    Send TTS via Home Assistant using tts.speak service (HA 2024+).
    Uses direct HA REST API when running as addon.
    
    Args:
        message: The text to speak
        media_player: Target media player entity_id
        volume: Volume level 0.0-1.0
        wait_for_idle: Wait for media player to be idle before playing
        tts_service: TTS entity (e.g., tts.google_en_com) or legacy service name
        language: Optional language code
        cache: Whether to cache the TTS audio
    """
    if not message or not media_player:
        return False, "Message and media player required"
    media_player = media_player.strip()
    tts_service = tts_service.strip() if tts_service else "tts.google_translate_say"

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

    # Build service data for tts.speak (the modern HA way)
    service_data = {
        "media_player_entity_id": media_player,
        "message": message,
        "cache": cache,
    }
    
    # Only add language if non-empty
    if language and language.strip():
        service_data["language"] = language.strip()
    
    # Use tts.speak with target entity_id pointing to the TTS entity
    # This is how home-weather does it
    status, data = await _ha_request(
        "POST",
        "/api/services/tts/speak",
        {
            **service_data,
            "entity_id": tts_service,  # TTS entity as target
        },
    )
    
    if status in (200, 201):
        logger.info(f"TTS sent to {media_player} via tts.speak targeting {tts_service}")
        return True, ""
    
    # Fallback: try legacy format for older TTS services like tts.google_translate_say
    if "_say" in tts_service or "_speak" in tts_service:
        domain, service = tts_service.split(".", 1) if "." in tts_service else ("tts", "google_translate_say")
        status, data = await _ha_request(
            "POST",
            f"/api/services/{domain}/{service}",
            {"entity_id": media_player, "message": message},
        )
        if status in (200, 201):
            logger.info(f"TTS sent to {media_player} via legacy {domain}/{service}")
            return True, ""
    
    error_msg = f"TTS service returned {status}"
    if data and isinstance(data, dict) and data.get("message"):
        error_msg = f"{error_msg}: {data.get('message')}"
    
    return False, error_msg
