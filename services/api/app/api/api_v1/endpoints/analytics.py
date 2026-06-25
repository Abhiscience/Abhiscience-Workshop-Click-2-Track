"""Analytics and dashboard endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.core.security import decode_token
from app.schemas.schemas import UtilizationMetrics

router = APIRouter()

async def get_current_user():
    return {"user_id": 1}

@router.get("/dashboard/live-workshop-status")
async def get_live_workshop_status(
    branch_id: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get live status of all vehicles in workshop."""
    return {
        "active_vehicles": [],
        "vehicles_by_stage": {},
        "average_wait_times": {},
        "bottlenecks": []
    }

@router.get("/dashboard/utilization-metrics", response_model=UtilizationMetrics)
async def get_utilization_metrics(
    branch_id: str = None,
    date: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workshop utilization metrics."""
    return UtilizationMetrics(
        gate_to_advisor_minutes=0,
        advisor_to_technician_minutes=0,
        total_turnaround_minutes=0,
        capture_compliance_percent=0,
        bottleneck_stages=[]
    )

@router.get("/dashboard/manpower-summary")
async def get_manpower_summary(
    branch_id: str = None,
    date: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get daily manpower summary."""
    return {
        "users": [],
        "total_handled": {},
        "current_active": {},
        "stage_involvement": {}
    }

@router.get("/dashboard/deviation-summary")
async def get_deviation_summary(
    branch_id: str = None,
    date: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get deviation summary for dashboard."""
    return {
        "total_deviations": 0,
        "by_type": {},
        "by_severity": {},
        "resolved_count": 0
    }