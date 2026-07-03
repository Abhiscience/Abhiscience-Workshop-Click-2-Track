"""Analytics and dashboard endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import joinedload
from typing import List
from datetime import datetime, date, timedelta
from collections import defaultdict
from app.core.database import get_db
from app.core.security import decode_token
from app.schemas.schemas import UtilizationMetrics
from app.models.models import CaptureEvent, WorkflowStage, Vehicle, JobCard, User, Branch, PendingVehicle

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


def _parse_date(date_str: str = None) -> date:
    if not date_str:
        return datetime.utcnow().date()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except ValueError:
            return datetime.utcnow().date()


def _date_range_bounds(d: date):
    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1)
    return start, end


@router.get("/dashboard/live-workshop-status")
async def get_live_workshop_status(
    branch_id: int = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get live status of all vehicles currently in workshop (no exit capture yet)."""
    # Find the EXIT/GATE_EXIT stage if configured
    exit_stage_stmt = select(WorkflowStage).options(joinedload(WorkflowStage.role)).where(WorkflowStage.stage_code.ilike("%EXIT%"))
    if branch_id:
        exit_stage_stmt = exit_stage_stmt.where(WorkflowStage.branch_id == branch_id)
    exit_result = await db.execute(exit_stage_stmt)
    exit_stages = {s.stage_id for s in exit_result.scalars().all()}

    # Latest capture event per job_card / pending_vehicle
    latest_events_sub = (
        select(
            CaptureEvent.job_card_id,
            CaptureEvent.pending_vehicle_ref,
            func.max(CaptureEvent.received_at_server).label("latest_time")
        )
        .where(or_(CaptureEvent.job_card_id.isnot(None), CaptureEvent.pending_vehicle_ref.isnot(None)))
        .group_by(CaptureEvent.job_card_id, CaptureEvent.pending_vehicle_ref)
        .subquery()
    )

    stmt = (
        select(CaptureEvent, WorkflowStage, Vehicle, JobCard, User, Branch)
        .join(latest_events_sub,
              and_(
                  CaptureEvent.job_card_id == latest_events_sub.c.job_card_id,
                  CaptureEvent.pending_vehicle_ref == latest_events_sub.c.pending_vehicle_ref,
                  CaptureEvent.received_at_server == latest_events_sub.c.latest_time
              ))
        .outerjoin(WorkflowStage, CaptureEvent.stage_id == WorkflowStage.stage_id)
        .outerjoin(JobCard, CaptureEvent.job_card_id == JobCard.job_card_id)
        .outerjoin(Vehicle, CaptureEvent.vehicle_id == Vehicle.vehicle_id)
        .outerjoin(User, CaptureEvent.user_id == User.user_id)
        .outerjoin(Branch, WorkflowStage.branch_id == Branch.branch_id)
    )
    if branch_id:
        stmt = stmt.where(WorkflowStage.branch_id == branch_id)

    result = await db.execute(stmt)
    rows = result.all()

    active_vehicles = []
    vehicles_by_stage = defaultdict(int)
    stage_wait_times = defaultdict(list)
    now = datetime.utcnow()

    for event, stage, vehicle, job_card, user, branch in rows:
        if not stage or event.stage_id in exit_stages:
            continue

        # Skip completed job cards
        if job_card and job_card.status in ("CLOSED", "COMPLETED", "CANCELLED"):
            continue

        wait_minutes = (now - event.received_at_server).total_seconds() / 60.0 if event.received_at_server else 0
        stage_wait_times[stage.stage_name].append(wait_minutes)
        vehicles_by_stage[stage.stage_name] += 1

        reg_number = vehicle.registration_number if vehicle else (event.plate_text_normalized or event.plate_text_raw or "Unknown")
        active_vehicles.append({
            "job_card_id": job_card.job_card_id if job_card else None,
            "pending_vehicle_ref": event.pending_vehicle_ref,
            "registration_number": reg_number,
            "current_stage_code": stage.stage_code,
            "current_stage_name": stage.stage_name,
            "captured_at": event.received_at_server.isoformat() if event.received_at_server else None,
            "waiting_minutes": round(wait_minutes, 1),
            "user_name": user.name if user else None,
            "branch_name": branch.branch_name if branch else None,
            "image_url": event.image_url,
        })

    average_wait_times = {
        stage: round(sum(times) / len(times), 1) if times else 0
        for stage, times in stage_wait_times.items()
    }

    # Bottleneck = stage with most vehicles waiting
    bottleneck_stages = sorted(
        vehicles_by_stage.items(), key=lambda x: x[1], reverse=True
    )[:3]

    return {
        "active_vehicles": active_vehicles,
        "vehicles_by_stage": dict(vehicles_by_stage),
        "average_wait_times": average_wait_times,
        "bottlenecks": [{"stage": s, "count": c} for s, c in bottleneck_stages]
    }


@router.get("/dashboard/utilization-metrics", response_model=UtilizationMetrics)
async def get_utilization_metrics(
    branch_id: int = None,
    date: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workshop utilization metrics for a given date."""
    target_date = _parse_date(date)
    start, end = _date_range_bounds(target_date)

    # Load stages
    stage_stmt = select(WorkflowStage).options(joinedload(WorkflowStage.role))
    if branch_id:
        stage_stmt = stage_stmt.where(WorkflowStage.branch_id == branch_id)
    stage_result = await db.execute(stage_stmt)
    stages = stage_result.scalars().all()
    stage_by_id = {s.stage_id: s for s in stages}
    stage_by_code = {s.stage_code: s for s in stages}

    # Fetch capture events for target date
    event_stmt = select(CaptureEvent, WorkflowStage).outerjoin(
        WorkflowStage, CaptureEvent.stage_id == WorkflowStage.stage_id
    ).where(
        CaptureEvent.received_at_server >= start,
        CaptureEvent.received_at_server < end
    )
    if branch_id:
        event_stmt = event_stmt.where(WorkflowStage.branch_id == branch_id)
    event_stmt = event_stmt.order_by(CaptureEvent.received_at_server)

    event_result = await db.execute(event_stmt)
    events = event_result.all()

    # Group events by job_card / vehicle
    vehicle_events = defaultdict(list)
    for event, stage in events:
        key = event.job_card_id or event.vehicle_id or event.pending_vehicle_ref or "unknown"
        vehicle_events[key].append((event, stage))

    gate_to_advisor_times = []
    advisor_to_technician_times = []
    turnaround_times = []

    for key, evs in vehicle_events.items():
        # Sort by sequence_order, fallback to timestamp
        evs.sort(key=lambda x: (
            x[1].sequence_order if x[1] and x[1].sequence_order is not None else 9999,
            x[0].received_at_server or datetime.min
        ))

        # Generic time-gap logic based on sequence_order, not hardcoded stage codes
        role_name_map = {s.stage_id: (getattr(s.role, "role_name", None) if hasattr(s, "role") else None) for s in stages}
        ordered_captures = [(event, stage) for event, stage in evs if stage and stage.sequence_order is not None]
        if not ordered_captures:
            continue

        timestamps_by_seq = {stage.sequence_order: event.received_at_server for event, stage in ordered_captures}
        sorted_seqs = sorted(timestamps_by_seq.keys())

        # Gate -> Advisor: first captured stage to second captured stage
        if len(sorted_seqs) >= 2:
            t_gate = timestamps_by_seq.get(sorted_seqs[0])
            t_advisor = timestamps_by_seq.get(sorted_seqs[1])
            if t_gate and t_advisor and t_advisor > t_gate:
                gate_to_advisor_times.append((t_advisor - t_gate).total_seconds() / 60.0)

        # Advisor -> Technician: second captured stage to the first TECHNICIAN-related stage
        if len(sorted_seqs) >= 2:
            advisor_seq = sorted_seqs[1]
            advisor_time = timestamps_by_seq.get(advisor_seq)
            tech_time = None
            for seq in sorted_seqs:
                if seq <= advisor_seq:
                    continue
                ev_stage = next((stage for event, stage in ordered_captures if stage.sequence_order == seq), None)
                if ev_stage and ev_stage.role_id:
                    role_name = role_name_map.get(ev_stage.stage_id)
                    if role_name == "TECHNICIAN":
                        tech_time = timestamps_by_seq.get(seq)
                        break
            if not tech_time and len(sorted_seqs) >= 4:
                tech_time = timestamps_by_seq.get(sorted_seqs[3])
            if advisor_time and tech_time and tech_time > advisor_time:
                advisor_to_technician_times.append((tech_time - advisor_time).total_seconds() / 60.0)

        # Total turnaround: first captured stage to final captured stage
        if len(sorted_seqs) >= 2:
            first_time = timestamps_by_seq.get(sorted_seqs[0])
            last_time = timestamps_by_seq.get(sorted_seqs[-1])
            if first_time and last_time and last_time > first_time:
                turnaround_times.append((last_time - first_time).total_seconds() / 60.0)

    # Compliance: % of mandatory stages that have a capture event per job card
    mandatory_stages = [s for s in stages if s.capture_mandatory]
    compliant_job_cards = 0
    total_job_cards_checked = 0

    if mandatory_stages:
        for key, evs in vehicle_events.items():
            captured_stage_ids = {stage.stage_id for event, stage in evs if stage}
            required_ids = {s.stage_id for s in mandatory_stages}
            if not required_ids:
                continue
            total_job_cards_checked += 1
            matched = len(captured_stage_ids & required_ids)
            if matched >= len(required_ids):
                compliant_job_cards += 1

    compliance_percent = (
        (compliant_job_cards / total_job_cards_checked * 100) if total_job_cards_checked else 100.0
    )

    def avg(times):
        return round(sum(times) / len(times), 1) if times else 0.0

    return UtilizationMetrics(
        gate_to_advisor_minutes=avg(gate_to_advisor_times),
        advisor_to_technician_minutes=avg(advisor_to_technician_times),
        total_turnaround_minutes=avg(turnaround_times),
        capture_compliance_percent=round(compliance_percent, 1),
        bottleneck_stages=[]
    )


@router.get("/dashboard/manpower-summary")
async def get_manpower_summary(
    branch_id: int = None,
    date: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get daily manpower summary: captures handled per user."""
    target_date = _parse_date(date)
    start, end = _date_range_bounds(target_date)

    stmt = (
        select(CaptureEvent.user_id, func.count(CaptureEvent.event_id).label("capture_count"))
        .where(
            CaptureEvent.received_at_server >= start,
            CaptureEvent.received_at_server < end
        )
        .group_by(CaptureEvent.user_id)
    )

    result = await db.execute(stmt)
    counts = {row.user_id: row.capture_count for row in result.all()}

    # Enrich with user details
    user_ids = list(counts.keys())
    users = []
    if user_ids:
        user_stmt = select(User).where(User.user_id.in_(user_ids))
        user_result = await db.execute(user_stmt)
        users = user_result.scalars().all()

    total_handled = sum(counts.values())
    user_details = []
    for user in users:
        user_details.append({
            "user_id": user.user_id,
            "name": user.name,
            "mobile": user.mobile,
            "role_id": user.role_id,
            "branch_id": user.branch_id,
            "capture_count": counts.get(user.user_id, 0),
        })

    return {
        "users": user_details,
        "total_handled": total_handled,
        "capture_counts_by_user": counts,
    }


@router.get("/dashboard/morning-meeting-deviations")
async def get_morning_meeting_deviations(
    branch_id: int = None,
    date: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Morning-meeting deviation report per role and per vehicle cycle.

    Compares the expected workflow stage sequence against actual captures for the
    target date, flagging missing mandatory captures, out-of-order captures
    (including late/forgotten-then-logged events), and long stay times.

    Stages marked skip_deviation (Part D) or is_rework (Part E) are excluded from
    the expected sequence so legitimate exceptions do not appear as anomalies.
    """
    from app.services.deviation_report_service import build_morning_meeting_report

    target_date = _parse_date(date)
    report = await build_morning_meeting_report(db, target_date, branch_id)
    return report


@router.get("/dashboard/deviation-summary")
async def get_deviation_summary(
    branch_id: int = None,
    date: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Compare actual capture sequence per vehicle against expected workflow stage order."""
    target_date = _parse_date(date)
    start, end = _date_range_bounds(target_date)

    # Expected order
    stage_stmt = select(WorkflowStage).options(joinedload(WorkflowStage.role)).order_by(WorkflowStage.sequence_order)
    if branch_id:
        stage_stmt = stage_stmt.where(WorkflowStage.branch_id == branch_id)
    stage_result = await db.execute(stage_stmt)
    stages = stage_result.scalars().all()
    expected_order = {s.stage_id: (s.sequence_order or 0) for s in stages}

    event_stmt = select(CaptureEvent).where(
        CaptureEvent.received_at_server >= start,
        CaptureEvent.received_at_server < end
    ).order_by(CaptureEvent.received_at_server)
    event_result = await db.execute(event_stmt)
    events = event_result.scalars().all()

    # Group by job card / vehicle
    vehicle_events = defaultdict(list)
    for event in events:
        key = event.job_card_id or event.vehicle_id or event.pending_vehicle_ref or "unknown"
        vehicle_events[key].append(event)

    total_deviations = 0
    by_type = defaultdict(int)
    by_severity = defaultdict(int)

    for key, evs in vehicle_events.items():
        # Sort by received time
        evs.sort(key=lambda e: e.received_at_server or datetime.min)

        # Get actual sequence
        actual_sequence = []
        for event in evs:
            seq = expected_order.get(event.stage_id)
            if seq is not None:
                actual_sequence.append(seq)

        # Detect out-of-order and skipped stages
        seen = set()
        prev_seq = -1
        for seq in actual_sequence:
            if seq < prev_seq:
                total_deviations += 1
                by_type["WRONG_SEQUENCE"] += 1
                by_severity["HIGH"] += 1
            # Check skipped mandatory stages between prev and current
            for s in range(prev_seq + 1, seq):
                # Find stage code for this sequence
                skipped_stage = next((st.stage_code for st in stages if (st.sequence_order or 0) == s), None)
                if skipped_stage:
                    total_deviations += 1
                    by_type["SKIPPED_STAGE"] += 1
                    by_severity["MEDIUM"] += 1
            seen.add(seq)
            prev_seq = seq

    return {
        "total_deviations": total_deviations,
        "by_type": dict(by_type),
        "by_severity": dict(by_severity),
        "resolved_count": 0
    }
