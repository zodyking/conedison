"""
Send mobile_app notifications via Home Assistant REST API (addon with SUPERVISOR_TOKEN).
"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def notify_mobile(
    notify_entity: str,
    message: str,
    title: Optional[str] = None,
    actions: Optional[List[Dict[str, str]]] = None,
) -> tuple[bool, str]:
    """
    Call notify.<entity> (e.g. notify_entity='mobile_app_pixel').

    actions: [{"action": "ID", "title": "Label"}, ...] for mobile_app_notification_action.
    """
    notify_entity = (notify_entity or "").strip()
    if not notify_entity:
        return False, "Missing notify entity"
    if not message:
        return False, "Missing message"

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        logger.warning("SUPERVISOR_TOKEN not set — skipping HA notify")
        return False, "SUPERVISOR_TOKEN not set"

    from ha_tts import _ha_request

    path = f"/api/services/notify/{notify_entity}"
    body: Dict[str, Any] = {"message": message}
    if title:
        body["title"] = title
    if actions:
        body["data"] = {"actions": actions}

    status, data = await _ha_request("POST", path, body)
    if status in (200, 201):
        logger.info("HA notify sent to notify.%s", notify_entity)
        return True, ""
    err = f"notify returned {status}"
    if data and isinstance(data, dict) and data.get("message"):
        err = f"{err}: {data.get('message')}"
    logger.warning("HA notify failed: %s", err)
    return False, err
