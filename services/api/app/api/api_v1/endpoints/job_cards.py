"""Job card endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.core.security import decode_token
from app.schemas.schemas import JobCard as JobCardSchema, VehicleTimeline, DeviationResponse
from workflow_engine.deviation import DeviationEngine

router = APIRouter()

async def get_current_user():
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"user_id": user_id}

@router.get("/active/search")
async def search_active_job_cards(
    plate: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search active job cards by plate number."""
    # Placeholder - integrate with DMS adapter
    return {"job_cards": []}

@router.get("/{job_card_id}")
async def get_job_card(
    job_card_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific job card details."""
    return {"job_card_id": job_card_id}

@router.get("/{job_card_id}/timeline", response_model=VehicleTimeline)
async def get_vehicle_timeline(
    job_card_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get complete timeline for a vehicle/job card."""
    return VehicleTimeline(
        vehicle_id="veh_001",
        registration_number="A12345",
        job_card_id=job_card_id,
        events=[]
    )

@router.get("/{job_card_id}/deviations", response_model=List[DeviationResponse])
async def get_deviations(
    job_card_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get deviations for a job card."""
    engine = DeviationEngine()
    deviations = await engine.detect_deviations(job_card_id)
    return [
        DeviationResponse(
            deviation_type=d.deviation_type.value if hasattr(d.deviation_type, 'value') else str(d.deviation_type),
            stage_code=d.stage_code,
            description=d.description,
            expected_time=d.expected_time,
            actual_time=d.actual_time,
            severity=d.severity,
            details=d.details
        ) for d in deviations
    ]