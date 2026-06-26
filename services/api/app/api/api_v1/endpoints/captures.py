"""Capture event endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid
from datetime import datetime

from app.core.database import get_db
from app.models.models import CaptureEvent, MatchStatus, PendingVehicle
from app.schemas.schemas import CaptureEventCreate, CaptureEvent as CaptureEventSchema
from app.core.security import decode_token
from anpr_providers.base import get_provider, normalize_plate

router = APIRouter()

async def get_current_user():
    return {"user_id": 2}

@router.post("/", response_model=CaptureEventSchema)
async def create_capture(
    stage_id: str,
    remarks: str = None,
    image: UploadFile = File(None),
    plate_text: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new capture event with optional image."""
    # Generate event ID
    # event_id is auto-incremented
    
    # Handle image upload and OCR
    image_url = None
    image_hash = None
    ocr_plate = plate_text
    ocr_confidence = 0.95
    
    if image:
        import uuid as _uuid, hashlib
        image_bytes = await image.read()
        image_hash = hashlib.md5(image_bytes).hexdigest()
        image_url = f"/uploads/{_uuid.uuid4()}.jpg"
        try:
            provider = get_provider("UA")
            result = provider.recognize(image_bytes)
            if result.plate_text and result.plate_text != "UNKNOWN":
                ocr_plate = result.plate_text
                ocr_confidence = result.confidence
        except Exception as e:
            print(f"OCR error: {e}")
    
    # Create capture event
    event = CaptureEvent(
        stage_id=int(stage_id),
        user_id=current_user["user_id"],
        installation_id=1,
        image_url=image_url,
        image_hash=image_hash,
        plate_text_raw=ocr_plate,
        plate_text_normalized=normalize_plate(ocr_plate) if ocr_plate else None,
        plate_confidence=ocr_confidence,
        match_status=MatchStatus.PENDING_NO_JC,
        captured_at_device=datetime.utcnow(),
        remarks=remarks
    )
    
    db.add(event)
    await db.commit()
    await db.refresh(event)
    
    return event

@router.get("/")
async def list_captures(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List capture events for current user."""
    from sqlalchemy.future import select
    result = await db.execute(select(CaptureEvent).order_by(CaptureEvent.event_id.desc()).limit(50))
    events = result.scalars().all()
    return {"events": [{"event_id": e.event_id, "plate_text_raw": e.plate_text_raw, "plate_text_normalized": e.plate_text_normalized, "match_status": e.match_status, "captured_at_device": str(e.captured_at_device), "stage_id": e.stage_id} for e in events]}

@router.post("/{event_id}/confirm-match")
async def confirm_match(
    event_id: str,
    job_card_id: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm match between capture and job card."""
    # Placeholder implementation
    return {"status": "matched", "job_card_id": job_card_id}