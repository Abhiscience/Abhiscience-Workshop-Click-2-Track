"""Morning meeting deviation report builder.

This service compares a vehicle's actual capture sequence against the expected
workflow stage order and emits deviations that are useful for the daily
morning meeting: per-role and per-vehicle views, with support for excluding
legitimate rework cycles (Part E) and "not applicable" stages (Part D).
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.models import CaptureEvent, WorkflowStage, User, Role, JobCard, Vehicle


# Severity constants
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

# Deviation categories
DEV_MISSING_MANDATORY = "MISSING_MANDATORY_CAPTURE"
DEV_OUT_OF_ORDER = "OUT_OF_ORDER_CAPTURE"
DEV_LATE_CAPTURE = "LATE_CAPTURE"
DEV_LONG_WAIT = "LONG_WAIT"


async def _load_expected_stages(
    db: AsyncSession,
    branch_id: Optional[int],
) -> Dict[int, WorkflowStage]:
    """Load workflow stages. Returns dict keyed by stage_id.

    Excludes:
      - stages flagged skip_deviation (Part D "not applicable" stages)
      - stages flagged is_rework      (Part E legitimate rework cycles)
    """
    stmt = select(WorkflowStage).options(joinedload(WorkflowStage.role))
    if branch_id:
        stmt = stmt.where(WorkflowStage.branch_id == branch_id)
    result = await db.execute(stmt)
    stages = {
        s.stage_id: s
        for s in result.scalars().all()
        if not s.skip_deviation and not s.is_rework
    }
    return stages


async def _load_capture_events(
    db: AsyncSession,
    target_date: date,
    branch_id: Optional[int],
    stage_ids: set,
) -> List[CaptureEvent]:
    """Load capture events for the target date, eager-loading relations."""
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)

    stmt = (
        select(CaptureEvent)
        .options(
            joinedload(CaptureEvent.stage).joinedload(WorkflowStage.role),
            joinedload(CaptureEvent.user).joinedload(User.role),
            joinedload(CaptureEvent.job_card),
            joinedload(CaptureEvent.vehicle),
        )
        .where(
            CaptureEvent.received_at_server >= start,
            CaptureEvent.received_at_server < end,
        )
        .where(CaptureEvent.stage_id.in_(stage_ids))
        .order_by(CaptureEvent.received_at_server)
    )
    result = await db.execute(stmt)
    return list(result.scalars().unique())


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


async def build_morning_meeting_report(
    db: AsyncSession,
    target_date: Optional[date] = None,
    branch_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a deviation report for the morning meeting.

    Returns:
      - summary counts
      - per_role breakdowns
      - per_vehicle cycles with ideal vs actual sequence
    """
    target_date = target_date or datetime.utcnow().date()

    stages = await _load_expected_stages(db, branch_id)
    expected_order = {
        s.stage_id: idx for idx, s in enumerate(sorted(stages.values(), key=lambda x: x.sequence_order or 0))
    }
    stage_by_id = stages

    events = await _load_capture_events(db, target_date, branch_id, set(stages.keys()))

    # Group events by work item: prefer job_card, then vehicle, then pending ref.
    grouped: Dict[Any, List[CaptureEvent]] = defaultdict(list)
    for ev in events:
        key = ev.job_card_id or ev.vehicle_id or ev.pending_vehicle_ref or "unknown"
        grouped[key].append(ev)

    deviations: List[Dict[str, Any]] = []
    vehicles: List[Dict[str, Any]] = []
    per_role: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"deviation_count": 0, "deviations": []})

    for key, evs in grouped.items():
        # Sort once by server time
        evs.sort(key=lambda e: e.received_at_server or datetime.min)

        # Sequence of stage ids as actually captured (duplicated stages are kept for now
        # because rework detection will use is_rework later; for ordering analysis we
        # track first occurrence per stage).
        actual_ids = [e.stage_id for e in evs]
        actual_seqs = [expected_order.get(sid) for sid in actual_ids]

        vehicle_reg = None
        jc_display = None
        if evs[0].vehicle:
            vehicle_reg = evs[0].vehicle.registration_number
        if evs[0].job_card:
            jc_display = evs[0].job_card.external_job_card_no

        vehicle_deviations = []
        ideal_sequence = [
            {"stage_id": s.stage_id, "stage_name": s.stage_name, "stage_code": s.stage_code}
            for s in sorted(stages.values(), key=lambda x: x.sequence_order or 0)
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

        # 1. Missing mandatory captures
        mandatory_ids = {sid for sid, s in stages.items() if s.capture_mandatory}
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

        # 2. Out-of-order / late captures.
        # Walk actual captures; every time a lower-sequence stage appears after a
        # higher-sequence one, flag an out-of-order deviation.  We use the first
        # capture timestamp per stage to detect lateness/forgotten-then-logged
        # events.
        first_seen_index: Dict[int, int] = {}
        last_index = -1
        for idx, (sid, seq) in enumerate(zip(actual_ids, actual_seqs)):
            if seq is None:
                continue
            if sid in first_seen_index:
                # Duplicate (could be rework later); Part E will use is_rework so
                # non-rework duplicates here are anomalies.
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
        long_wait_dev = None
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
        "target_date": target_date.isoformat(),
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
