"""Morning meeting deviation report builder.

This service compares a vehicle's actual capture sequence against the expected
workflow stage order and emits deviations that are useful for the daily
morning meeting: per-role and per-vehicle views.

Rework handling (Part E):
  Some stages (e.g. WORK_STARTED) are reused for legitimate rework cycles. A
  repeated stage_id is treated as legitimate rework — and therefore NOT flagged
  as a deviation — ONLY when a QC stage (PRE_ROAD_TEST_QC by default) occurs
  between the previous capture of that stage and the repeat. Otherwise the repeat
  is a genuine duplicate/error.

Part D "not applicable" stages are excluded via two mechanisms:
  1. A static WorkflowStage.skip_deviation flag excludes a stage globally.
  2. A per-job-card JobCardNotApplicableStage row excludes a stage for a
     specific job card (with a required reason). Those stages are treated as
     compliant in all calculations.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.models import CaptureEvent, WorkflowStage, User, Role, JobCard, Vehicle
from app.services.not_applicable_service import get_not_applicable_stage_ids


# Severity constants
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

# Deviation categories
DEV_MISSING_MANDATORY = "MISSING_MANDATORY_CAPTURE"
DEV_OUT_OF_ORDER = "OUT_OF_ORDER_CAPTURE"
DEV_DUPLICATE = "DUPLICATE_CAPTURE"
DEV_LONG_WAIT = "LONG_WAIT"

# Stage codes that act as QC/rework boundary markers. A repeated stage after one of
# these is treated as legitimate rework.
REWORK_QC_STAGE_CODES: Set[str] = {"PRE_ROAD_TEST_QC"}


def _match_status_value(ms):
    return ms.value if hasattr(ms, "value") else str(ms)


async def _load_expected_stages(
    db: AsyncSession,
    branch_id: Optional[int],
) -> Dict[int, WorkflowStage]:
    """Load workflow stages, excluding those marked skip_deviation (Part D)."""
    stmt = select(WorkflowStage).options(joinedload(WorkflowStage.role))
    if branch_id:
        stmt = stmt.where(WorkflowStage.branch_id == branch_id)
    result = await db.execute(stmt)
    stages = {
        s.stage_id: s
        for s in result.scalars().all()
        if not s.skip_deviation
    }
    return stages


async def _load_capture_events_range(
    db: AsyncSession,
    start_dt: datetime,
    end_dt: datetime,
    stage_ids: set,
) -> List[CaptureEvent]:
    """Load capture events for a datetime range, eager-loading relations.

    Excludes:
      - voided captures
      - captures attached to CANCELLED job cards
    """
    stmt = (
        select(CaptureEvent)
        .options(
            joinedload(CaptureEvent.stage).joinedload(WorkflowStage.role),
            joinedload(CaptureEvent.user).joinedload(User.role),
            joinedload(CaptureEvent.job_card),
            joinedload(CaptureEvent.vehicle),
        )
        .outerjoin(JobCard, CaptureEvent.job_card_id == JobCard.job_card_id)
        .where(
            CaptureEvent.received_at_server >= start_dt,
            CaptureEvent.received_at_server < end_dt,
            CaptureEvent.voided == False,
            or_(
                CaptureEvent.job_card_id.is_(None),
                JobCard.status != "CANCELLED",
            ),
        )
        .where(CaptureEvent.stage_id.in_(stage_ids))
        .order_by(CaptureEvent.received_at_server)
    )
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


async def _load_capture_events(
    db: AsyncSession,
    target_date: date,
    stage_ids: set,
) -> List[CaptureEvent]:
    """Load capture events for the target date, eager-loading relations.

    Excludes:
      - voided captures (Part D correction mechanism)
      - captures attached to CANCELLED job cards
    """
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    return await _load_capture_events_range(db, start, end, stage_ids)


async def _select_role_name(stage: Optional[WorkflowStage]) -> Optional[str]:
    if not stage:
        return None
    if stage.role and stage.role.role_name:
        return stage.role.role_name
    # Fallback: derive a generic role bucket from stage_code if known.
    code = (stage.stage_code or "").upper()
    if "TECH" in code or "MECHANIC" in code:
        return "TECHNICIAN"
    if "ADVISOR" in code or "SERVICE_ADVISOR" in code or "SA" == code:
        return "ADVISOR"
    if "PARTS" in code:
        return "PARTS"
    if "QUALITY" in code or "QC" in code or "INSPECTION" in code:
        return "QUALITY"
    if "WASH" in code or "CLEAN" in code:
        return "WASHING"
    return None


def _is_qc_between(
    events: List[CaptureEvent],
    prev_idx: int,
    curr_idx: int,
) -> bool:
    """Return True if a QC stage occurs between prev_idx and curr_idx (exclusive)."""
    for ev in events[prev_idx + 1:curr_idx]:
        if ev.stage and ev.stage.stage_code in REWORK_QC_STAGE_CODES:
            return True
    return False


async def build_morning_meeting_report(
    db: AsyncSession,
    target_date: Optional[date] = None,
    branch_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a deviation report for the morning meeting (single day view)."""
    target_date = target_date or datetime.utcnow().date()
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    return await build_deviation_report_range(db, start, end, branch_id)


async def build_deviation_report_range(
    db: AsyncSession,
    start_dt: datetime,
    end_dt: datetime,
    branch_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a deviation report for an arbitrary datetime range."""
    stages = await _load_expected_stages(db, branch_id)
    expected_order = {
        s.stage_id: idx for idx, s in enumerate(sorted(stages.values(), key=lambda x: x.sequence_order or 0))
    }
    stage_by_id = stages

    events = await _load_capture_events_range(db, start_dt, end_dt, set(stages.keys()))

    # Group events by work item: prefer job_card, then vehicle, then pending ref,
    # then plate_text_normalized, only falling back to "unknown" as last resort.
    def _group_key(ev: CaptureEvent) -> Any:
        return ev.job_card_id or ev.vehicle_id or ev.pending_vehicle_ref or ev.plate_text_normalized or "unknown"

    grouped: Dict[Any, List[CaptureEvent]] = defaultdict(list)
    for ev in events:
        key = _group_key(ev)
        grouped[key].append(ev)

    deviations: List[Dict[str, Any]] = []
    vehicles: List[Dict[str, Any]] = []
    per_role: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"deviation_count": 0, "deviations": []})

    for key, evs in grouped.items():
        # Sort once by server time
        evs.sort(key=lambda e: e.received_at_server or datetime.min)

        actual_ids = [e.stage_id for e in evs]
        actual_seqs = [expected_order.get(sid) for sid in actual_ids]

        # Determine job_card_id if any event has one
        job_card_id = None
        for e in evs:
            if e.job_card_id:
                job_card_id = e.job_card_id
                break

        # Per-job-card not-applicable stages (Part D)
        na_stage_ids = await get_not_applicable_stage_ids(db, job_card_id) if job_card_id else set()

        vehicle_reg = None
        jc_display = None
        if evs[0].vehicle:
            vehicle_reg = evs[0].vehicle.registration_number
        if evs[0].job_card:
            jc_display = evs[0].job_card.external_job_card_no

        vehicle_deviations = []
        # Build ideal sequence excluding globally skipped and per-job N/A stages
        ideal_sequence = [
            {"stage_id": s.stage_id, "stage_name": s.stage_name, "stage_code": s.stage_code}
            for s in sorted(stages.values(), key=lambda x: x.sequence_order or 0)
            if s.stage_id not in na_stage_ids
        ]
        actual_sequence = [
            {
                "event_id": e.event_id,
                "stage_id": e.stage_id,
                "stage_name": e.stage.stage_name if e.stage else None,
                "stage_code": e.stage.stage_code if e.stage else None,
                "role_name": (e.stage.role.role_name if e.stage and e.stage.role else await _select_role_name(e.stage)),
                "user_name": e.user.name if e.user else None,
                "user_id": e.user_id,
                "captured_at": e.received_at_server.isoformat() if e.received_at_server else None,
            }
            for e in evs
        ]

        # 1. Missing mandatory captures (exclude N/A stages and already captured stages).
        mandatory_ids = {sid for sid, s in stages.items() if s.capture_mandatory and sid not in na_stage_ids}
        captured_ids = set(actual_ids)
        for sid in sorted(mandatory_ids, key=lambda x: expected_order.get(x, 9999)):
            if sid not in captured_ids:
                stage = stage_by_id.get(sid)
                role_name = None
                if stage and stage.role:
                    role_name = stage.role.role_name
                dev = {
                    "type": DEV_MISSING_MANDATORY,
                    "severity": SEVERITY_HIGH,
                    "stage_id": sid,
                    "stage_name": stage.stage_name if stage else None,
                    "stage_code": stage.stage_code if stage else None,
                    "role_name": role_name,
                    "description": f"Missing mandatory capture: {stage.stage_name if stage else sid}",
                    "job_card_id": key if isinstance(key, int) and jc_display else None,
                    "vehicle_registration": vehicle_reg,
                    "user_id": None,
                    "user_name": None,
                }
                deviations.append(dev)
                vehicle_deviations.append(dev)
                if role_name:
                    per_role[role_name]["deviation_count"] += 1
                    per_role[role_name]["deviations"].append(dev)

        # 2. Out-of-order / duplicate captures with dynamic rework detection.
        first_seen_index: Dict[int, int] = {}
        last_index = -1
        for idx, (sid, seq) in enumerate(zip(actual_ids, actual_seqs)):
            if seq is None:
                continue
            # If this stage is marked N/A for this job, skip anomaly flagging entirely
            # (it should not have been captured; if it was, we ignore it for compliance).
            if sid in na_stage_ids:
                continue

            prev_idx = first_seen_index.get(sid)
            if prev_idx is not None:
                if _is_qc_between(evs, prev_idx, idx):
                    continue
                else:
                    stage = stage_by_id.get(sid)
                    role_name = None
                    if stage and stage.role:
                        role_name = stage.role.role_name
                    dev = {
                        "type": DEV_DUPLICATE,
                        "severity": SEVERITY_MEDIUM,
                        "stage_id": sid,
                        "stage_name": stage.stage_name if stage else None,
                        "stage_code": stage.stage_code if stage else None,
                        "role_name": role_name,
                        "description": f"{stage.stage_name if stage else sid} captured again without QC/rework boundary",
                        "job_card_id": key if isinstance(key, int) and jc_display else None,
                        "vehicle_registration": vehicle_reg,
                        "user_id": evs[idx].user_id,
                        "user_name": evs[idx].user.name if evs[idx].user else None,
                    }
                    deviations.append(dev)
                    vehicle_deviations.append(dev)
                    if role_name:
                        per_role[role_name]["deviation_count"] += 1
                        per_role[role_name]["deviations"].append(dev)
                    continue

            first_seen_index[sid] = idx
            if seq < last_index:
                stage = stage_by_id.get(sid)
                role_name = None
                if stage and stage.role:
                    role_name = stage.role.role_name
                dev = {
                    "type": DEV_OUT_OF_ORDER,
                    "severity": SEVERITY_MEDIUM,
                    "stage_id": sid,
                    "stage_name": stage.stage_name if stage else None,
                    "stage_code": stage.stage_code if stage else None,
                    "role_name": role_name,
                    "description": (
                        f"{stage.stage_name if stage else sid} captured out of order "
                        "(logged late or skipped earlier)"
                    ),
                    "job_card_id": key if isinstance(key, int) and jc_display else None,
                    "vehicle_registration": vehicle_reg,
                    "user_id": evs[idx].user_id,
                    "user_name": evs[idx].user.name if evs[idx].user else None,
                }
                deviations.append(dev)
                vehicle_deviations.append(dev)
                if role_name:
                    per_role[role_name]["deviation_count"] += 1
                    per_role[role_name]["deviations"].append(dev)
            last_index = max(last_index, seq)

        # Optional long-wait rule: if first and last capture span > 8 hours.
        times = [e.received_at_server for e in evs if e.received_at_server]
        if len(times) >= 2:
            span = (max(times) - min(times)).total_seconds() / 3600.0
            if span > 8:
                long_wait_dev = {
                    "type": DEV_LONG_WAIT,
                    "severity": SEVERITY_LOW,
                    "stage_id": None,
                    "stage_name": None,
                    "stage_code": None,
                    "role_name": None,
                    "description": f"Vehicle cycle spanned {round(span, 1)} hours",
                    "job_card_id": key if isinstance(key, int) and jc_display else None,
                    "vehicle_registration": vehicle_reg,
                    "user_id": None,
                    "user_name": None,
                }
                deviations.append(long_wait_dev)
                vehicle_deviations.append(long_wait_dev)

        vehicles.append({
            "job_card_id": key if isinstance(key, int) and jc_display else None,
            "vehicle_id": key if isinstance(key, int) and not jc_display and vehicle_reg else None,
            "vehicle_registration": vehicle_reg,
            "external_job_card_no": jc_display,
            "ideal_sequence": ideal_sequence,
            "actual_sequence": actual_sequence,
            "deviations": vehicle_deviations,
            "deviation_count": len(vehicle_deviations),
            "not_applicable_stage_ids": list(na_stage_ids),
        })

    # Sort vehicles by most deviations first.
    vehicles.sort(key=lambda v: v["deviation_count"], reverse=True)

    total_deviations = len(deviations)
    by_type = defaultdict(int)
    by_severity = defaultdict(int)
    for d in deviations:
        by_type[d["type"]] += 1
        by_severity[d["severity"]] += 1

    return {
        "period_start": start_dt.isoformat(),
        "period_end": end_dt.isoformat(),
        "target_date": start_dt.date().isoformat(),
        "branch_id": branch_id,
        "summary": {
            "total_deviations": total_deviations,
            "vehicles_with_deviations": sum(1 for v in vehicles if v["deviation_count"] > 0),
            "total_vehicles_reviewed": len(vehicles),
            "by_type": dict(by_type),
            "by_severity": dict(by_severity),
        },
        "per_role": dict(per_role),
        "per_vehicle": vehicles,
        "deviations": deviations,
    }
