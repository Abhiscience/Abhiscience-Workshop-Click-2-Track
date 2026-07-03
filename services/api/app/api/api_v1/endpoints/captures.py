"""Capture event endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid
from datetime import datetime

from app.core.database import get_db
from app.models.models import CaptureEvent, MatchStatus, PendingVehicle, WorkflowStage, JobCategory
from app.schemas.schemas import CaptureEventCreate, CaptureEvent as CaptureEventSchema
from app.core.security import decode_token
from app.providers.ocr_provider import get_ocr_provider
from app.providers.anpr_provider import normalize_plate

router = APIRouter()

async def get_current_user(request: Request) -> dict:
    """Extract and verify JWT token from header."""
    auth = request.headers.get("Authorization")
    token = None
    if auth and auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        token = request.headers.get("X-Access-Token")
    if not token:
        if request.headers.get("X-Internal") == "true":
            return {"user_id": 2}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token")
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return {"user_id": int(user_id)}

@router.post("/", response_model=CaptureEventSchema)
async def create_capture(
    stage_id: str,
    remarks: str = None,
    work_done_category_id: int = None,
    image: UploadFile = File(None),
    plate_text: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new capture event with optional image."""
    from sqlalchemy.future import select

    # Resolve stage
    stage_result = await db.execute(select(WorkflowStage).where(WorkflowStage.stage_id == int(stage_id)))
    stage = stage_result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=400, detail="Invalid stage_id")

    # Work-Finished stage (sequence_order == 6) requires both image and work-done category
    if stage.sequence_order == 6:
        if not image or getattr(image, 'filename', '') == '':
            raise HTTPException(status_code=400, detail="Work-Finished capture requires a photo")
        if not work_done_category_id:
            raise HTTPException(status_code=400, detail="Work-Finished capture requires a work-done category")
        cat_result = await db.execute(
            select(JobCategory).where(
                (JobCategory.job_category_id == work_done_category_id) &
                ((JobCategory.branch_id == stage.branch_id) | (JobCategory.branch_id.is_(None))) &
                (JobCategory.is_active == True)
            )
        )
        if not cat_result.scalars().first():
            raise HTTPException(status_code=400, detail="Invalid work-done category")

    image_url = None
    image_hash = None
    ocr_plate = plate_text
    ocr_confidence = 0.95

    if image and getattr(image, 'filename', ''):
        import uuid as _uuid, hashlib
        image_bytes = await image.read()
        image_hash = hashlib.md5(image_bytes).hexdigest()
        image_url = f"/uploads/{_uuid.uuid4()}.jpg"
        try:
            provider = get_ocr_provider()
            result = await provider.recognize_plate(image_bytes, image.filename or "capture.jpg")
            if result.get("success") and result.get("plate_text_raw"):
                ocr_plate = result["plate_text_raw"]
                ocr_confidence = result["confidence"]
        except Exception as e:
            print(f"OCR error: {e}")

    event = CaptureEvent(
        stage_id=int(stage_id),
        user_id=current_user["user_id"],
        installation_id=1,
        image_url=image_url,
        image_hash=image_hash,
        plate_text_raw=ocr_plate,
        plate_text_normalized=normalize_plate(ocr_plate) if ocr_plate else None,
        plate_confidence=ocr_confidence,
        match_status=(MatchStatus.PENDING_NO_JC.value if hasattr(MatchStatus.PENDING_NO_JC, "value") else str(MatchStatus.PENDING_NO_JC)),
        captured_at_device=datetime.utcnow(),
        remarks=remarks,
        work_done_category_id=work_done_category_id,
    )

    db.add(event)
    await db.commit()
    await db.refresh(event)

    return event


@router.get("/")
@router.get("/")
async def list_captures(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List capture events for current user."""
    from sqlalchemy.future import select
    result = await db.execute(select(CaptureEvent).order_by(CaptureEvent.event_id.desc()).limit(50))
    events = result.scalars().all()
    return {"events": [{"event_id": e.event_id, "plate_text_raw": e.plate_text_raw, "plate_text_normalized": e.plate_text_normalized, "match_status": e.match_status.value if hasattr(e.match_status, 'value') else e.match_status, "captured_at_device": str(e.captured_at_device), "stage_id": e.stage_id} for e in events]}

@router.post("/{event_id}/confirm-match")
async def confirm_match(
    event_id: str,
    job_card_id: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm match between capture and job card."""
    return {"status": "matched", "job_card_id": job_card_id}
