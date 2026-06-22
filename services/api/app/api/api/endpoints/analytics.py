from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from core.database import get_db
from core.security import decode_token
from api.schemas.schemas import AnalyticsMetrics
from models.models import JobCard, CaptureEvent, User, WorkflowStage, Role
from services.deviation_service import calculate_branch_utilization, calculate_analytics

router = APIRouter(prefix="/dashboards", tags=["analytics"])


async def get_current_user(token: dict = Depends(decode_token), db: AsyncSession = Depends(get_db)):
    """Dependency to get current user from token"""
    user_id = int(token.get("sub"))
    stmt = select(User).where(User.user_id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/utilization", response_model=AnalyticsMetrics)
async def get_utilization(
    branch_id: Optional[int] = None,
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get branch utilization analytics"""
    # In production, would verify user has access to this branch
    target_branch = branch_id or current_user.branch_id
    
    utilization = await calculate_branch_utilization(db, target_branch, hours)
    analytics = await calculate_analytics(db, target_branch)
    
    return AnalyticsMetrics(
        gate_to_jc_open_minutes=analytics.get("gate_to_jc_open_minutes"),
        jc_open_to_technician_accept_minutes=analytics.get("jc_open_to_technician_accept_minutes"),
        technician_to_parts_wait_minutes=analytics.get("technician_to_parts_wait_minutes"),
        parts_wait_to_parts_issue_minutes=analytics.get("parts_wait_to_parts_issue_minutes"),
        wash_tat_minutes=analytics.get("wash_tat_minutes"),
        qc_tat_minutes=analytics.get("qc_tat_minutes"),
        total_workshop_tat_minutes=analytics.get("total_workshop_tat_minutes"),
        capture_compliance_percent=analytics.get("capture_compliance_percent"),
        branch_stage_bottleneck_index=analytics.get("branch_stage_bottleneck_index")
    )