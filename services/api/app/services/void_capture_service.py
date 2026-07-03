"""Capture void/correction service (Part D).

Never hard-deletes a capture. Instead marks the original event as voided and
optionally creates a replacement event linked back to the original.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import CaptureEvent


async def void_capture(
    db: AsyncSession,
    event_id: int,
    voided_by_user_id: int,
    reason: str,
    corrected_event_id: Optional[int] = None,
) -> CaptureEvent:
    if not reason or not reason.strip():
        raise ValueError("reason is required")

    event_result = await db.execute(select(CaptureEvent).where(CaptureEvent.event_id == event_id))
    event = event_result.scalar_one_or_none()
    if not event:
        raise ValueError("Capture event not found")
    if event.voided:
        raise ValueError("Capture event is already voided")

    event.voided = True
    event.voided_at = datetime.utcnow()
    event.voided_by = voided_by_user_id
    event.void_reason = reason.strip()
    event.corrected_event_id = corrected_event_id
    await db.flush()
    return event


async def create_correction_capture(
    db: AsyncSession,
    original_event_id: int,
    correction_data: dict,
) -> CaptureEvent:
    """Create a corrected capture linked to the original voided event."""
    original_result = await db.execute(select(CaptureEvent).where(CaptureEvent.event_id == original_event_id))
    original = original_result.scalar_one_or_none()
    if not original:
        raise ValueError("Original capture event not found")

    new_event = CaptureEvent(
        stage_id=correction_data.get("stage_id", original.stage_id),
        user_id=correction_data.get("user_id", original.user_id),
        installation_id=correction_data.get("installation_id", original.installation_id),
        job_card_id=correction_data.get("job_card_id", original.job_card_id),
        vehicle_id=correction_data.get("vehicle_id", original.vehicle_id),
        pending_vehicle_ref=correction_data.get("pending_vehicle_ref", original.pending_vehicle_ref),
        image_url=correction_data.get("image_url", original.image_url),
        image_hash=correction_data.get("image_hash", original.image_hash),
        plate_text_raw=correction_data.get("plate_text_raw", original.plate_text_raw),
        plate_text_normalized=correction_data.get("plate_text_normalized", original.plate_text_normalized),
        plate_confidence=correction_data.get("plate_confidence", original.plate_confidence),
        match_status=correction_data.get("match_status", original.match_status),
        match_method=correction_data.get("match_method", original.match_method or "manual_correction"),
        captured_at_device=correction_data.get("captured_at_device", datetime.utcnow()),
        received_at_server=datetime.utcnow(),
        geo_lat=correction_data.get("geo_lat", original.geo_lat),
        geo_lng=correction_data.get("geo_lng", original.geo_lng),
        remarks=correction_data.get("remarks", original.remarks),
        work_done_category_id=correction_data.get("work_done_category_id", original.work_done_category_id),
        corrected_event_id=None,  # corrections are not themselves voided; original points here
    )
    db.add(new_event)
    await db.flush()

    # Link original to the correction
    original.corrected_event_id = new_event.event_id
    await db.flush()
    return new_event
