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
    return {"user_id": 1}

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
    event_id = f"evt_{str(uuid.uuid4())[:8]}"
    
    # Handle image upload
    image_url = None
    image_hash = None
    
    if image:
        # Upload to object storage (MinIO/S3)
        # For now, placeholder
        image_url = f"/uploads/{event_id}.jpg"
        image_hash = "hash_placeholder"
    
    # Create capture event
    event = CaptureEvent(
        event_id=event_id,
        stage_id=stage_id,
        user_id=current_user["user_id"],
        installation_id="inst_001",  # From header
        image_url=image_url,
        image_hash=image_hash,
        plate_text_raw=plate_text,
        plate_text_normalized=normalize_plate(plate_text) if plate_text else None,
        plate_confidence=0.95,
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
    return {"events": []}

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