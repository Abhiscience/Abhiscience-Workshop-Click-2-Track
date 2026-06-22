from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List

from core.database import get_db
from core.security import decode_token
from api.schemas.schemas import (
    VehicleResponse,
    VehicleCreate,
    VehicleTimeline,
    VehicleTimelineEvent
)
from models.models import Vehicle, User
from services.deviation_service import get_vehicle_timeline

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


async def get_current_user(token: dict = Depends(decode_token), db: AsyncSession = Depends(get_db)):
    """Dependency to get current user from token"""
    user_id = int(token.get("sub"))
    stmt = select(User).where(User.user_id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=VehicleResponse)
async def create_vehicle(
    vehicle_create: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new vehicle"""
    # Check if registration already exists
    existing_stmt = select(Vehicle).where(Vehicle.registration_number == vehicle_create.registration_number)
    if (await db.execute(existing_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Registration number already exists")
    
    vehicle = Vehicle(**vehicle_create.model_dump())
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    
    return VehicleResponse(
        vehicle_id=vehicle.vehicle_id,
        registration_number=vehicle.registration_number,
        make=vehicle.make,
        model=vehicle.model,
        color=vehicle.color,
        customer_id=vehicle.customer_id
    )


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific vehicle"""
    stmt = select(Vehicle).where(Vehicle.vehicle_id == vehicle_id)
    vehicle = (await db.execute(stmt)).scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    return VehicleResponse(
        vehicle_id=vehicle.vehicle_id,
        registration_number=vehicle.registration_number,
        make=vehicle.make,
        model=vehicle.model,
        color=vehicle.color,
        customer_id=vehicle.customer_id
    )


@router.get("/{vehicle_id}/timeline", response_model=VehicleTimeline)
async def get_vehicle_timeline_endpoint(
    vehicle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get timeline of capture events for a vehicle"""
    # Verify vehicle exists
    stmt = select(Vehicle).where(Vehicle.vehicle_id == vehicle_id)
    vehicle = (await db.execute(stmt)).scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    timeline = await get_vehicle_timeline(db, vehicle_id)
    
    return VehicleTimeline(
        vehicle_id=vehicle_id,
        registration_number=vehicle.registration_number,
        timeline=timeline
    )