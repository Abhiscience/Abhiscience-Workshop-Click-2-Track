from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List

from core.database import get_db
from core.security import decode_token
from api.schemas.schemas import JobCardResponse, JobCardCreate
from models.models import JobCard, Vehicle, Branch, User

router = APIRouter(prefix="/job-cards", tags=["job-cards"])


async def get_current_user(token: dict = Depends(decode_token), db: AsyncSession = Depends(get_db)):
    """Dependency to get current user from token"""
    user_id = int(token.get("sub"))
    stmt = select(User).where(User.user_id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/active/search", response_model=List[JobCardResponse])
async def search_active_job_cards(
    plate: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search active job cards by plate or branch"""
    conditions = []
    
    # Only get open/in_progress job cards
    conditions.append(JobCard.status.in_(["open", "in_progress"]))
    
    if plate:
        # Join with vehicle to search by registration
        conditions.append(Vehicle.registration_number.ilike(f"%{plate}%"))
    
    if branch_id:
        conditions.append(JobCard.branch_id == branch_id)
    
    stmt = select(JobCard).join(Vehicle).where(*conditions).order_by(JobCard.open_time.desc()).limit(50)
    
    job_cards = (await db.execute(stmt)).scalars().all()
    
    return [JobCardResponse(
        job_card_id=jc.job_card_id,
        external_job_card_no=jc.external_job_card_no,
        vehicle_id=jc.vehicle_id,
        branch_id=jc.branch_id,
        advisor_id=jc.advisor_id,
        status=jc.status,
        open_time=jc.open_time,
        close_time=jc.close_time
    ) for jc in job_cards]


@router.get("/{job_card_id}", response_model=JobCardResponse)
async def get_job_card(
    job_card_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific job card"""
    stmt = select(JobCard).where(JobCard.job_card_id == job_card_id)
    job_card = (await db.execute(stmt)).scalar_one_or_none()
    
    if not job_card:
        raise HTTPException(status_code=404, detail="Job card not found")
    
    return JobCardResponse(
        job_card_id=job_card.job_card_id,
        external_job_card_no=job_card.external_job_card_no,
        vehicle_id=job_card.vehicle_id,
        branch_id=job_card.branch_id,
        advisor_id=job_card.advisor_id,
        status=job_card.status,
        open_time=job_card.open_time,
        close_time=job_card.close_time
    )


@router.post("/", response_model=JobCardResponse)
async def create_job_card(
    job_card_create: JobCardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new job card"""
    # Verify vehicle exists
    vehicle_stmt = select(Vehicle).where(Vehicle.vehicle_id == job_card_create.vehicle_id)
    vehicle = (await db.execute(vehicle_stmt)).scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=400, detail="Invalid vehicle ID")
    
    # Verify branch exists
    branch_stmt = select(Branch).where(Branch.branch_id == job_card_create.branch_id)
    branch = (await db.execute(branch_stmt)).scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=400, detail="Invalid branch ID")
    
    # Check external job card number is unique
    existing_stmt = select(JobCard).where(JobCard.external_job_card_no == job_card_create.external_job_card_no)
    if (await db.execute(existing_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Job card number already exists")
    
    job_card = JobCard(
        external_job_card_no=job_card_create.external_job_card_no,
        vehicle_id=job_card_create.vehicle_id,
        branch_id=job_card_create.branch_id,
        advisor_id=job_card_create.advisor_id,
        status=job_card_create.status
    )
    
    db.add(job_card)
    await db.commit()
    await db.refresh(job_card)
    
    return JobCardResponse(
        job_card_id=job_card.job_card_id,
        external_job_card_no=job_card.external_job_card_no,
        vehicle_id=job_card.vehicle_id,
        branch_id=job_card.branch_id,
        advisor_id=job_card.advisor_id,
        status=job_card.status,
        open_time=job_card.open_time,
        close_time=job_card.close_time
    )