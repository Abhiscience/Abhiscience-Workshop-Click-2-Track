"""Push notification services for mobile app_installations.push_token.

Supports Expo push tokens by default (matches the mobile app setup). If the
project later moves to FCM, extend `send_push_notification` with a provider
branch while keeping the public API unchanged.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_push_notification(
    push_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> dict:
    """Send a single push notification.

    Returns a metadata dict with `success` (bool), `provider` and the raw
    response detail. Errors are swallowed so callers can decide whether to
    escalate; this keeps capture/approval flows from failing because of a
    downstream push-provider hiccup.
    """
    if not push_token or push_token.lower() in {"null", "none", ""}:
        return {"success": False, "provider": None, "error": "No push token"}

    # Expo push tokens look like "ExponentPushToken[xxxxx]"
    if push_token.startswith("ExponentPushToken"):
        return await _send_expo(push_token, title, body, data)

    # Lightweight FCM fallback detection.  Leave unimplemented unless the
    # project supplies Firebase credentials; we still return structured info.
    if push_token.startswith("d") and len(push_token) >= 100:
        return {"success": False, "provider": "fcm", "error": "FCM sender not configured"}

    return {"success": False, "provider": "unknown", "error": f"Unrecognized token format: {push_token[:20]}"}


async def _send_expo(
    push_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> dict:
    payload = {
        "to": push_token,
        "title": title,
        "body": body,
        "sound": "default",
        "priority": "high",
        "channelId": "override-requests",
    }
    if data:
        payload["data"] = data

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                EXPO_PUSH_URL,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body_json = response.json()
            logger.info("Expo push response: %s", body_json)
            return {
                "success": body_json.get("data", {}).get("status") == "ok",
                "provider": "expo",
                "response": body_json,
            }
    except Exception as exc:  # pragma: no cover - external service
        logger.exception("Failed to send Expo push to %s", push_token)
        return {"success": False, "provider": "expo", "error": str(exc)}


def build_override_request_title(requester_name: str, stage_name: str) -> str:
    return f"Override needed: {requester_name} at {stage_name}"


def build_override_decision_title(stage_name: str, approved: bool) -> str:
    status = "approved" if approved else "denied"
    return f"Override {status}: {stage_name}"
