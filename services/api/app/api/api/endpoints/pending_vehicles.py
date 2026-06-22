from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from datetime import datetime

from core.database import get_db
from core.security import decode_token
from api.schemas.schemas import PendingVehicleResponse, PendingVehicleCreate
from models.models import PendingVehicle, User, Branch

router = APIRouter(prefix="/pending-vehicles", tags=["pending-vehicles"])


async def get_current_user(token: dict = Depends(decode_token), db: AsyncSession = Depends(get_db)):
    """Dependency to get current user from token"""
    user_id = int(token.get("sub"))
    stmt = select(User).where(User.user_id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/", response_model=List[PendingVehicleResponse])
async def list_pending_vehicles(
    branch_id: Optional[int] = None,
    link_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List pending vehicles with optional filtering"""
    conditions = []
    
    if branch_id:
        conditions.append(PendingVehicle.branch_id == branch_id)
    elif current_user.branch_id:
        conditions.append(PendingVehicle.branch_id == current_user.branch_id)
    
    if link_status:
        conditions.append(PendingVehicle.link_status == link_status)
    
    stmt = select(PendingVehicle)
    if conditions:
        stmt = stmt.where(*conditions)
    
    stmt = stmt.order_by(PendingVehicle.created_at.desc()).offset(skip).limit(limit)
    
    pending_vehicles = (await db.execute(stmt)).scalars().all()
    
    return [PendingVehicleResponse(
        pending_vehicle_ref=pv.pending_vehicle_ref,
        temporary_plate_text=pv.temporary_plate_text,
        gate_event_id=pv.gate_event_id,
        branch_id=pv.branch_id,
        created_at=pv.created_at,
        link_status=pv.link_status
    ) for pv in pending_vehicles]


@router.post("/", response_model=PendingVehicleResponse)
async def create_pending_vehicle(
    pending_create: PendingVehicleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a pending vehicle entry"""
    pending = PendingVehicle(**pending_create.model_dump())
    db.add(pending)
    await db.commit()
    await db.refresh(pending)
    
    return PendingVehicleResponse(
        pending_vehicle_ref=pending.pending_vehicle_ref,
        temporary_plate_text=pending.temporary_plate_text,
        gate_event_id=pending.gate_event_id,
        branch_id=pending.branch_id,
        created_at=pending.created_at,
        link_status=pending.link_status
    )


@router.post("/{pending_vehicle_ref}/link-job-card", response_model=PendingVehicleResponse)
async def link_job_card(
    pending_vehicle_ref: int,
    vehicle_id: int,
    job_card_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Link a pending vehicle to a job card"""
    stmt = select(PendingVehicle).where(PendingVehicle.pending_vehicle_ref == pending_vehicle_ref)
    pending = (await db.execute(stmt)).scalar_one_or_none()
    
    if not pending:
        raise HTTPException(status_code=404, detail="Pending vehicle not found")
    
    # In production, would verify vehicle and job card exist and match branch
    pending.link_status = "LINKED"  # Could be more specific
    
    await db.commit()
    await db.refresh(pending)
    
    return PendingVehicleResponse(
        pending_vehicle_ref=pending.pending_vehicle_ref,
        temporary_plate_text=pending.temporary_plate_text,
        gate_event_id=pending.gate_event_id,
        branch_id=pending.branch_id,
        created_at=pending.created_at,
        link_status=pending.link_status
    )