from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import (
    CaptureEvent,
    JobCard,
    WorkflowStage,
    Branch,
    Vehicle,
    PendingVehicle
)


MATCH_STATUSES = ["EXACT_MATCH", "NORMALIZED_MATCH", "SHORTLIST_REQUIRED", "MANUAL_CONFIRMED", "PENDING_NO_JC", "UNMATCHED"]


async def detect_deviation(
    db: AsyncSession,
    event: CaptureEvent,
    vehicle_id: Optional[int] = None,
    branch_id: int = None
) -> Dict[str, Any]:
    """
    Detect workflow deviations for a capture event.
    
    Returns deviation details including:
    - Expected stage vs actual stage
    - Missing captures
    - Timing anomalies
    """
    result = {
        "has_deviation": False,
        "deviation_type": None,
        "details": {}
    }
    
    # Get the stage for this event
    stmt = select(WorkflowStage).where(WorkflowStage.stage_id == event.stage_id)
    stage = (await db.execute(stmt)).scalar_one_or_none()
    
    if not stage:
        return result
    
    # Check if there are missing mandatory captures for previous stages
    prev_stages_stmt = select(WorkflowStage).where(
        and_(
            WorkflowStage.branch_id == branch_id,
            WorkflowStage.sequence_order < stage.sequence_order,
            WorkflowStage.capture_mandatory == True
        )
    ).order_by(WorkflowStage.sequence_order)
    
    prev_stages = (await db.execute(prev_stages_stmt)).scalars().all()
    
    if prev_stages:
        for prev_stage in prev_stages:
            prev_capture_stmt = select(CaptureEvent).where(
                and_(
                    CaptureEvent.job_card_id == event.job_card_id,
                    CaptureEvent.stage_id == prev_stage.stage_id
                )
            )
            prev_capture = (await db.execute(prev_capture_stmt)).scalar_one_or_none()
            
            if not prev_capture:
                result["has_deviation"] = True
                result["deviation_type"] = "MISSING_MANDATORY_CAPTURE"
                result["details"]["missing_stage"] = prev_stage.stage_name
                break
    
    # Check timing - vehicle in workshop too long without progress
    if event.job_card_id:
        jc_stmt = select(JobCard).where(JobCard.job_card_id == event.job_card_id)
        job_card = (await db.execute(jc_stmt)).scalar_one_or_none()
        
        if job_card:
            time_in_workshop = datetime.utcnow() - job_card.open_time
            
            # Check if TAT exceeds threshold (e.g., 8 hours for standard service)
            if time_in_workshop > timedelta(hours=8):
                result["has_deviation"] = True
                result["deviation_type"] = "LONG_WAIT_TIME"
                result["details"]["hours_in_workshop"] = time_in_workshop.total_seconds() / 3600
    
    return result


async def calculate_branch_utilization(
    db: AsyncSession,
    branch_id: int,
    hours: int = 24
) -> Dict[str, Any]:
    """
    Calculate branch utilization metrics.
    """
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # Count captures in time window
    captures_stmt = select(func.count(CaptureEvent.event_id)).where(
        and_(
            CaptureEvent.captured_at_device >= since,
            CaptureEvent.vehicle_id.is_not(None)
        )
    )
    capture_count = (await db.execute(captures_stmt)).scalar()
    
    # Count active job cards
    active_jc_stmt = select(func.count(JobCard.job_card_id)).where(
        and_(
            JobCard.branch_id == branch_id,
            JobCard.status == "open"
        )
    )
    active_jc_count = (await db.execute(active_jc_stmt)).scalar()
    
    # Calculate compliance rate
    total_captures = capture_count or 0
    
    return {
        "branch_id": branch_id,
        "period_hours": hours,
        "total_captures": total_captures,
        "active_job_cards": active_jc_count,
        "captures_per_job_card": total_captures / active_jc_count if active_jc_count > 0 else 0
    }


async def get_vehicle_timeline(
    db: AsyncSession,
    vehicle_id: int
) -> List[Dict[str, Any]]:
    """
    Get complete timeline of capture events for a vehicle.
    """
    stmt = select(CaptureEvent).where(
        CaptureEvent.vehicle_id == vehicle_id
    ).order_by(CaptureEvent.captured_at_device)
    
    events = (await db.execute(stmt)).scalars().all()
    
    timeline = []
    for event in events:
        stage = (await db.execute(
            select(WorkflowStage).where(WorkflowStage.stage_id == event.stage_id)
        )).scalar_one_or_none()
        
        timeline.append({
            "event_id": event.event_id,
            "stage_name": stage.stage_name if stage else "Unknown",
            "plate_text": event.plate_text_normalized,
            "captured_at": event.captured_at_device,
            "image_url": event.image_url,
            "match_status": event.match_status
        })
    
    return timeline


async def calculate_analytics(
    db: AsyncSession,
    branch_id: Optional[int] = None,
    days: int = 30
) -> Dict[str, Any]:
    """
    Calculate comprehensive analytics for the dashboard.
    """
    since = datetime.utcnow() - timedelta(days=days)
    
    # Base query conditions
    conditions = [CaptureEvent.captured_at_device >= since]
    if branch_id:
        conditions.append(CaptureEvent.vehicle_id == branch_id)  # Will join properly
    
    # Gate to JC open time (from pending vehicles)
    pending_stmt = select(PendingVehicle).where(
        and_(
            PendingVehicle.link_status == "PENDING_NO_JC",
            PendingVehicle.created_at >= since
        )
    )
    # This would need actual timing data
    
    # Capture compliance
    total_events_stmt = select(func.count(CaptureEvent.event_id))
    matched_events_stmt = select(func.count(CaptureEvent.event_id)).where(
        and_(
            CaptureEvent.captured_at_device >= since,
            CaptureEvent.match_status.in_(["EXACT_MATCH", "NORMALIZED_MATCH"])
        )
    )
    
    total_events = (await db.execute(total_events_stmt)).scalar() or 0
    matched_events = (await db.execute(matched_events_stmt)).scalar() or 0
    
    compliance = (matched_events / total_events * 100) if total_events > 0 else 0
    
    return {
        "gate_to_jc_open_minutes": None,
        "jc_open_to_technician_accept_minutes": None,
        "technician_to_parts_wait_minutes": None,
        "parts_wait_to_parts_issue_minutes": None,
        "wash_tat_minutes": None,
        "qc_tat_minutes": None,
        "total_workshop_tat_minutes": None,
        "capture_compliance_percent": compliance,
        "branch_stage_bottleneck_index": None
    }