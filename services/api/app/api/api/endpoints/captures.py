from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from typing import Optional, List
import hashlib

from core.database import get_db
from core.security import decode_token, verify_password
from api.schemas.schemas import (
    CaptureEventCreate,
    CaptureEventResponse,
    CaptureEventConfirmMatch
)
from models.models import (
    CaptureEvent,
    JobCard,
    Vehicle,
    WorkflowStage,
    User,
    PendingVehicle
)
from providers.anpr_provider import recognize_plate
from services.deviation_service import detect_deviation

router = APIRouter(prefix="/captures", tags=["captures"])


async def get_current_user(token: dict = Depends(decode_token), db: AsyncSession = Depends(get_db)):
    """Dependency to get current user from token"""
    user_id = int(token.get("sub"))
    stmt = select(User).where(User.user_id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def normalize_plate(plate: str) -> str:
    """Normalize plate text for matching"""
    if not plate:
        return ""
    return plate.upper().replace("-", "").replace(" ", "")


@router.post("/", response_model=CaptureEventResponse)
async def create_capture(
    event_create: CaptureEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new capture event - matches plate to job card"""
    # Verify stage exists
    stage_stmt = select(WorkflowStage).where(WorkflowStage.stage_id == event_create.stage_id)
    stage = (await db.execute(stage_stmt)).scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=400, detail="Invalid stage ID")
    
    # Create capture event with initial status
    event = CaptureEvent(
        stage_id=event_create.stage_id,
        user_id=current_user.user_id,
        installation_id=event_create.installation_id,
        image_url=event_create.image_url,
        geo_lat=event_create.geo_lat,
        geo_lng=event_create.geo_lng,
        remarks=event_create.remarks,
        captured_at_device=datetime.utcnow(),
        received_at_server=datetime.utcnow(),
        match_status="UNMATCHED"
    )
    
    db.add(event)
    await db.flush()  # Get event_id without commit
    
    # Perform ANPR if image URL provided
    if event_create.image_url:
        anpr_result = await recognize_plate(event_create.image_url)
        
        if anpr_result["success"] and anpr_result["plate_text_raw"]:
            event.plate_text_raw = anpr_result["plate_text_raw"]
            event.plate_text_normalized = normalize_plate(anpr_result["plate_text_raw"])
            event.plate_confidence = anpr_result["confidence"]
            
            # Try to match to job card
            match_result = await match_plate_to_jobcard(
                db, 
                event.plate_text_normalized,
                stage.branch_id
            )
            
            if match_result["matched"]:
                event.job_card_id = match_result["job_card_id"]
                event.vehicle_id = match_result["vehicle_id"]
                event.match_status = match_result["match_status"]
                event.match_method = match_result["match_method"]
            else:
                # Create pending vehicle
                pending = PendingVehicle(
                    temporary_plate_text=event.plate_text_normalized,
                    branch_id=stage.branch_id,
                    link_status="PENDING_NO_JC"
                )
                db.add(pending)
                await db.flush()
                event.pending_vehicle_ref = pending.pending_vehicle_ref
                event.match_status = "PENDING_NO_JC"
    
    await db.commit()
    await db.refresh(event)
    
    return CaptureEventResponse(
        event_id=event.event_id,
        job_card_id=event.job_card_id,
        vehicle_id=event.vehicle_id,
        pending_vehicle_ref=event.pending_vehicle_ref,
        stage_id=event.stage_id,
        user_id=event.user_id,
        installation_id=event.installation_id,
        image_url=event.image_url,
        plate_text_raw=event.plate_text_raw,
        plate_text_normalized=event.plate_text_normalized,
        plate_confidence=event.plate_confidence,
        match_status=event.match_status,
        match_method=event.match_method,
        captured_at_device=event.captured_at_device,
        received_at_server=event.received_at_server,
        geo_lat=event.geo_lat,
        geo_lng=event.geo_lng,
        remarks=event.remarks
    )


async def match_plate_to_jobcard(
    db: AsyncSession,
    plate_text: str,
    branch_id: int
) -> dict:
    """
    Match plate to active job cards.
    Returns match status and job card details.
    """
    # Try exact match first - get vehicle with this plate
    vehicle_stmt = select(Vehicle).where(Vehicle.registration_number == plate_text)
    vehicle = (await db.execute(vehicle_stmt)).scalar_one_or_none()
    
    if vehicle:
        # Find active job card for this vehicle in this branch
        jc_stmt = select(JobCard).where(
            JobCard.vehicle_id == vehicle.vehicle_id,
            JobCard.branch_id == branch_id,
            JobCard.status.in_(["open", "in_progress"])
        ).order_by(JobCard.open_time.desc())
        
        job_card = (await db.execute(jc_stmt)).scalar_one_or_none()
        
        if job_card:
            return {
                "matched": True,
                "job_card_id": job_card.job_card_id,
                "vehicle_id": vehicle.vehicle_id,
                "match_status": "EXACT_MATCH",
                "match_method": "exact"
            }
    
    # Try normalized match - vehicles with similar plate
    similar_stmt = select(Vehicle).where(
        Vehicle.registration_number.ilike(f"%{plate_text}%")
    )
    similar_vehicles = (await db.execute(similar_stmt)).scalars().all()
    
    if similar_vehicles:
        # Get active job cards for these vehicles
        for veh in similar_vehicles:
            jc_stmt = select(JobCard).where(
                JobCard.vehicle_id == veh.vehicle_id,
                JobCard.branch_id == branch_id,
                JobCard.status.in_(["open", "in_progress"])
            ).order_by(JobCard.open_time.desc())
            
            job_card = (await db.execute(jc_stmt)).scalar_one_or_none()
            if job_card:
                return {
                    "matched": True,
                    "job_card_id": job_card.job_card_id,
                    "vehicle_id": veh.vehicle_id,
                    "match_status": "NORMALIZED_MATCH",
                    "match_method": "similarity"
                }
    
    return {"matched": False}


@router.post("/{event_id}/confirm-match", response_model=CaptureEventResponse)
async def confirm_match(
    event_id: int,
    confirm: CaptureEventConfirmMatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually confirm match for a capture event"""
    stmt = select(CaptureEvent).where(CaptureEvent.event_id == event_id)
    event = (await db.execute(stmt)).scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Capture event not found")
    
    if confirm.job_card_id:
        # Verify job card exists
        jc_stmt = select(JobCard).where(JobCard.job_card_id == confirm.job_card_id)
        job_card = (await db.execute(jc_stmt)).scalar_one_or_none()
        if not job_card:
            raise HTTPException(status_code=400, detail="Invalid job card ID")
        
        event.job_card_id = confirm.job_card_id
        event.vehicle_id = job_card.vehicle_id
        event.match_status = "MANUAL_CONFIRMED"
        event.match_method = confirm.match_method or "manual"
    
    await db.commit()
    await db.refresh(event)
    
    return CaptureEventResponse(
        event_id=event.event_id,
        job_card_id=event.job_card_id,
        vehicle_id=event.vehicle_id,
        pending_vehicle_ref=event.pending_vehicle_ref,
        stage_id=event.stage_id,
        user_id=event.user_id,
        installation_id=event.installation_id,
        image_url=event.image_url,
        plate_text_raw=event.plate_text_raw,
        plate_text_normalized=event.plate_text_normalized,
        plate_confidence=event.plate_confidence,
        match_status=event.match_status,
        match_method=event.match_method,
        captured_at_device=event.captured_at_device,
        received_at_server=event.received_at_server,
        geo_lat=event.geo_lat,
        geo_lng=event.geo_lng,
        remarks=event.remarks
    )


@router.get("/", response_model=List[CaptureEventResponse])
async def list_captures(
    skip: int = 0,
    limit: int = 100,
    stage_id: Optional[int] = None,
    match_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List capture events with optional filtering"""
    conditions = []
    
    if stage_id:
        conditions.append(CaptureEvent.stage_id == stage_id)
    if match_status:
        conditions.append(CaptureEvent.match_status == match_status)
    
    stmt = select(CaptureEvent)
    if conditions:
        stmt = stmt.where(*conditions)
    
    stmt = stmt.order_by(CaptureEvent.captured_at_device.desc()).offset(skip).limit(limit)
    
    events = (await db.execute(stmt)).scalars().all()
    
    return [CaptureEventResponse(
        event_id=e.event_id,
        job_card_id=e.job_card_id,
        vehicle_id=e.vehicle_id,
        pending_vehicle_ref=e.pending_vehicle_ref,
        stage_id=e.stage_id,
        user_id=e.user_id,
        installation_id=e.installation_id,
        image_url=e.image_url,
        plate_text_raw=e.plate_text_raw,
        plate_text_normalized=e.plate_text_normalized,
        plate_confidence=e.plate_confidence,
        match_status=e.match_status,
        match_method=e.match_method,
        captured_at_device=e.captured_at_device,
        received_at_server=e.received_at_server,
        geo_lat=e.geo_lat,
        geo_lng=e.geo_lng,
        remarks=e.remarks
    ) for e in events]


@router.get("/{event_id}", response_model=CaptureEventResponse)
async def get_capture(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific capture event"""
    stmt = select(CaptureEvent).where(CaptureEvent.event_id == event_id)
    event = (await db.execute(stmt)).scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Capture event not found")
    
    return CaptureEventResponse(
        event_id=event.event_id,
        job_card_id=event.job_card_id,
        vehicle_id=event.vehicle_id,
        pending_vehicle_ref=event.pending_vehicle_ref,
        stage_id=event.stage_id,
        user_id=event.user_id,
        installation_id=event.installation_id,
        image_url=event.image_url,
        plate_text_raw=event.plate_text_raw,
        plate_text_normalized=event.plate_text_normalized,
        plate_confidence=event.plate_confidence,
        match_status=event.match_status,
        match_method=event.match_method,
        captured_at_device=event.captured_at_device,
        received_at_server=event.received_at_server,
        geo_lat=event.geo_lat,
        geo_lng=event.geo_lng,
        remarks=event.remarks
    )