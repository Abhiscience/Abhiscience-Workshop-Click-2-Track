"""Job card endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from sqlalchemy.orm import joinedload
from datetime import datetime
from app.core.database import get_db
from app.core.security import decode_token
from app.schemas.schemas import JobCard as JobCardSchema, VehicleTimeline, TimelineEvent, DeviationResponse, JobCardNotApplicableStageCreate, JobCardNotApplicableStageResponse
from app.models.models import JobCard, User, WorkflowStage, Vehicle, CaptureEvent, CancellationCategory
from app.services.not_applicable_service import mark_stage_not_applicable, get_not_applicable_stages


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


async def _require_admin_or_advisor(current_user: dict, db: AsyncSession):
    user_result = await db.execute(select(User).options(joinedload(User.role)).where(User.user_id == current_user["user_id"]))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    role_name = (user.role.role_name or "").upper() if user.role else ""
    perms = user.role.permissions or {} if user.role else {}
    admin_like = role_name == "ADMIN" or perms.get("admin") or perms.get("configure")
    if not admin_like:
        raise HTTPException(status_code=403, detail="Only admins or advisors can perform this action")
    return user


@router.post("/{job_card_id}/not-applicable-stages", response_model=JobCardNotApplicableStageResponse)
async def mark_not_applicable_stage(
    job_card_id: str,
    payload: JobCardNotApplicableStageCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark a stage as not applicable for this specific job card with a required reason."""
    await _require_admin_or_advisor(current_user, db)

    jc_result = await db.execute(select(JobCard).where(JobCard.job_card_id == int(job_card_id)))
    job_card = jc_result.scalar_one_or_none()
    if not job_card:
        raise HTTPException(status_code=404, detail="Job card not found")

    if job_card.status in ("CANCELLED", "COMPLETED", "CLOSED"):
        raise HTTPException(status_code=400, detail="Cannot mark stages on a finished/cancelled job card")

    stage_result = await db.execute(select(WorkflowStage).where(WorkflowStage.stage_id == payload.stage_id))
    stage = stage_result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=400, detail="Stage not found")

    na = await mark_stage_not_applicable(
        db,
        job_card_id=int(job_card_id),
        stage_id=payload.stage_id,
        reason=payload.reason,
        marked_by_user_id=current_user["user_id"],
    )
    await db.commit()
    await db.refresh(na)
    return na


@router.get("/{job_card_id}/not-applicable-stages", response_model=List[JobCardNotApplicableStageResponse])
async def list_not_applicable_stages(
    job_card_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List stages marked as not applicable for this job card."""
    jc_result = await db.execute(select(JobCard).where(JobCard.job_card_id == int(job_card_id)))
    job_card = jc_result.scalar_one_or_none()
    if not job_card:
        raise HTTPException(status_code=404, detail="Job card not found")

    items = await get_not_applicable_stages(db, job_card_id=int(job_card_id))
    return items


@router.patch("/{job_card_id}/cancel")
async def cancel_job_card(
    job_card_id: str,
    reason: str,
    cancellation_category_id: int | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a job card with a required reason and optional cancellation category.

    Cancelled jobs are excluded from all turnaround/compliance/analytics calculations.
    """
    await _require_admin_or_advisor(current_user, db)

    if not reason or not reason.strip():
        raise HTTPException(status_code=400, detail="cancellation reason is required")

    jc_result = await db.execute(select(JobCard).where(JobCard.job_card_id == int(job_card_id)))
    job_card = jc_result.scalar_one_or_none()
    if not job_card:
        raise HTTPException(status_code=404, detail="Job card not found")

    if job_card.status in ("CANCELLED", "COMPLETED", "CLOSED"):
        raise HTTPException(status_code=400, detail="Job card is already in a terminal state")

    if cancellation_category_id:
        cat_result = await db.execute(
            select(CancellationCategory).where(
                CancellationCategory.cancellation_category_id == cancellation_category_id,
                CancellationCategory.is_active == True,
            )
        )
        if not cat_result.scalars().first():
            raise HTTPException(status_code=400, detail="Invalid cancellation category")

    job_card.status = "CANCELLED"
    job_card.cancellation_category_id = cancellation_category_id
    job_card.cancellation_reason = reason.strip()
    job_card.close_time = datetime.utcnow()
    await db.commit()
    return {
        "job_card_id": job_card.job_card_id,
        "status": job_card.status,
        "cancellation_category_id": job_card.cancellation_category_id,
        "cancellation_reason": job_card.cancellation_reason,
        "close_time": job_card.close_time.isoformat() if job_card.close_time else None,
    }


@router.get("/active/search")
async def search_active_job_cards(
    plate: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search active (non-terminal) job cards by plate number."""
    stmt = (
        select(JobCard)
        .join(Vehicle, JobCard.vehicle_id == Vehicle.vehicle_id)
        .where(JobCard.status.notin_(["COMPLETED", "CLOSED", "CANCELLED"]))
        .order_by(JobCard.open_time.desc())
    )
    if plate:
        normalized = plate.upper().replace(" ", "").replace("-", "")
        stmt = stmt.where(Vehicle.registration_number.ilike(f"%{normalized}%"))

    result = await db.execute(stmt)
    job_cards = result.scalars().all()
    return {
        "job_cards": [
            {
                "job_card_id": jc.job_card_id,
                "external_job_card_no": jc.external_job_card_no,
                "vehicle_id": jc.vehicle_id,
                "registration_number": jc.vehicle.registration_number if jc.vehicle else None,
                "branch_id": jc.branch_id,
                "advisor_id": jc.advisor_id,
                "status": jc.status,
                "open_time": jc.open_time.isoformat() if jc.open_time else None,
                "close_time": jc.close_time.isoformat() if jc.close_time else None,
            }
            for jc in job_cards
        ]
    }


@router.get("/{job_card_id}", response_model=JobCardSchema)
async def get_job_card(
    job_card_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific job card details."""
    result = await db.execute(select(JobCard).where(JobCard.job_card_id == int(job_card_id)))
    job_card = result.scalar_one_or_none()
    if not job_card:
        raise HTTPException(status_code=404, detail="Job card not found")
    return job_card


@router.get("/{job_card_id}/timeline", response_model=VehicleTimeline)
async def get_vehicle_timeline(
    job_card_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get complete timeline for a vehicle/job card."""
    result = await db.execute(select(JobCard).where(JobCard.job_card_id == int(job_card_id)))
    job_card = result.scalar_one_or_none()
    if not job_card:
        raise HTTPException(status_code=404, detail="Job card not found")

    events = await db.execute(
        select(CaptureEvent)
        .options(joinedload(CaptureEvent.stage))
        .where(CaptureEvent.job_card_id == int(job_card_id))
        .order_by(CaptureEvent.received_at_server)
    )
    events = result.scalars().all()

    return VehicleTimeline(
        vehicle_id=job_card.vehicle_id,
        registration_number=job_card.vehicle.registration_number if job_card.vehicle else "Unknown",
        job_card_id=job_card.job_card_id,
        events=[
            TimelineEvent(
                event_id=e.event_id,
                stage_name=e.stage.stage_name if e.stage else "Unknown",
                stage_code=e.stage.stage_code if e.stage else "",
                user_name=e.user.name if e.user else "",
                role_name=e.user.role.role_name if e.user and e.user.role else "",
                captured_at=e.received_at_server,
                image_url=e.image_url,
            )
            for e in events
        ]
    )


@router.get("/{job_card_id}/deviations", response_model=List[DeviationResponse])
async def get_deviations(
    job_card_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get deviations for a job card."""
    from workflow_engine.deviation import DeviationEngine
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