"""Part F: staff performance, rework rate, utilization and shortage analytics."""
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from math import radians, sin, cos, sqrt, atan2

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.models.models import (
    CaptureEvent, JobCard, User, Role, WorkflowStage, Vehicle,
    UserShift, StaffTarget, DemoRevenueEntry,
)


class _StaffPerformanceService:
    """Generic per-individual and per-role performance rollups.

    Works for any user/role configured in the system. No hardcoded role names.
    """

    EXCLUDED_STATUSES = {"CANCELLED", "ZERO_BILLED"}

    @classmethod
    async def rollup(
        cls,
        db: AsyncSession,
        start_dt: datetime,
        end_dt: datetime,
        branch_id: Optional[int] = None,
        role_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        stmt = (
            select(CaptureEvent)
            .options(
                joinedload(CaptureEvent.user).joinedload(User.role),
                joinedload(CaptureEvent.stage),
                joinedload(CaptureEvent.job_card),
            )
            .where(
                CaptureEvent.received_at_server >= start_dt,
                CaptureEvent.received_at_server < end_dt,
                CaptureEvent.voided == False,
            )
            .where(
                or_(
                    CaptureEvent.job_card_id.is_(None),
                    JobCard.status.notin_(list(cls.EXCLUDED_STATUSES)),
                )
            )
            .outerjoin(JobCard, CaptureEvent.job_card_id == JobCard.job_card_id)
        )
        if branch_id:
            stmt = stmt.where(CaptureEvent.branch_id == branch_id) if hasattr(CaptureEvent, "branch_id") else stmt
        result = await db.execute(stmt)
        events = result.scalars().unique().all()

        by_user: Dict[int, dict] = {}
        by_role: Dict[int, dict] = {}
        user_ids = set()
        job_card_ids = set()
        for ev in events:
            user = ev.user
            role = user.role if user else None
            uid = user.user_id if user else None
            rid = role.role_id if role else None

            if uid is not None and role_id and rid != role_id:
                continue

            if uid is not None:
                user_ids.add(uid)
                entry = by_user.setdefault(uid, {
                    "user_id": uid,
                    "user_name": user.name,
                    "role_id": rid,
                    "role_name": role.role_name if role else None,
                    "capture_count": 0,
                    "vehicle_registration_set": set(),
                    "job_card_ids": set(),
                    "technician_time_minutes": 0.0,
                    "cycle_count": 0,
                    "rework_cycle_count": 0,
                    "stage_breakdown": defaultdict(int),
                })
                entry["capture_count"] += 1
                entry["stage_breakdown"][(ev.stage.stage_code or "UNKNOWN")] += 1
                if ev.job_card_id:
                    entry["job_card_ids"].add(ev.job_card_id)
                else:
                    # Use plate/vehicle as work-identifier fallback
                    ident = ev.plate_text_normalized or ev.plate_text_raw
                    if ident:
                        entry["vehicle_registration_set"].add(ident)

            if rid is not None:
                role_entry = by_role.setdefault(rid, {
                    "role_id": rid,
                    "role_name": role.role_name if role else None,
                    "user_ids": set(),
                    "capture_count": 0,
                    "job_card_ids": set(),
                    "vehicle_registration_set": set(),
                    "cycle_count": 0,
                    "rework_cycle_count": 0,
                })
                role_entry["capture_count"] += 1
                role_entry["user_ids"].add(uid)
                if ev.job_card_id:
                    role_entry["job_card_ids"].add(ev.job_card_id)
                else:
                    ident = ev.plate_text_normalized or ev.plate_text_raw
                    if ident:
                        role_entry["vehicle_registration_set"].add(ident)

        # Load job-card/vehicle registration mapping in bulk.
        job_card_map = {}
        if job_card_ids:
            jc_result = await db.execute(
                select(JobCard.job_card_id, Vehicle.registration_number)
                .outerjoin(Vehicle, JobCard.vehicle_id == Vehicle.vehicle_id)
                .where(JobCard.job_card_id.in_(list(job_card_ids)))
            )
            for jcid, reg in jc_result.all():
                job_card_map[jcid] = reg

        # Compute technician time and rework cycles per job card.
        from app.services.technician_time_service import _TechnicianTimeService
        jc_ids = {ev.job_card_id for ev in events if ev.job_card_id}
        for jcid in jc_ids:
            report = await _TechnicianTimeService.build_report(db, jcid)
            if not report:
                continue
            cycles = report.get("cycles", [])
            total_cycles = len(cycles)
            for idx, cycle in enumerate(cycles):
                tech_id = cycle.get("technician_id")
                if tech_id and tech_id in by_user:
                    by_user[tech_id]["technician_time_minutes"] += cycle.get("net_work_minutes") or 0
                    by_user[tech_id]["cycle_count"] += 1
                    if idx > 0:
                        by_user[tech_id]["rework_cycle_count"] += 1

                for role_entry in by_role.values():
                    if tech_id and role_entry["role_id"] == (by_user.get(tech_id, {}).get("role_id")):
                        role_entry["cycle_count"] += 1
                        if idx > 0:
                            role_entry["rework_cycle_count"] += 1

        # Finalise serialisable output.
        def _finalise(entry):
            job_ids = entry.get("job_card_ids", set())
            regs = entry.get("vehicle_registration_set", set())
            vehicle_count = job_ids | regs
            return {
                "user_id": entry["user_id"],
                "name": entry.get("user_name"),
                "role_id": entry.get("role_id"),
                "role_name": entry.get("role_name"),
                "capture_count": entry.get("capture_count", 0),
                "vehicles_handled_count": len(vehicle_count),
                "cumulative_technician_minutes": entry.get("technician_time_minutes", 0.0),
                "rework_cycles_detected": entry.get("rework_cycle_count", 0),
            }

        users_out = [_finalise(e) for e in by_user.values()]
        if role_id:
            users_out = [u for u in users_out if u["role_id"] == role_id]

        roles_out = []
        for r in by_role.values():
            rid = r["role_id"]
            role_users = [u for u in users_out if u["role_id"] == rid]
            r.update({
                "total_captures": r.pop("capture_count", 0),
                "total_vehicles_handled": len(r.pop("job_card_ids", set()) | r.pop("vehicle_registration_set", set())),
                "total_technician_minutes": sum(u["cumulative_technician_minutes"] for u in role_users),
                "user_count": len(r.pop("user_ids", set())),
                "users": role_users,
            })
            roles_out.append(r)

        return {
            "period_start": start_dt.isoformat(),
            "period_end": end_dt.isoformat(),
            "branch_id": branch_id,
            "total_captures": len(events),
            "per_individual": sorted(users_out, key=lambda x: x["capture_count"], reverse=True),
            "per_role": sorted(roles_out, key=lambda x: x["total_captures"], reverse=True),
        }


class _VehicleFlowDashboardService:
    """Build a data structure suitable for the oval/loop vehicle-flow diagram."""

    @classmethod
    async def build(
        cls,
        db: AsyncSession,
        start_dt: datetime,
        end_dt: datetime,
        branch_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        stage_stmt = select(WorkflowStage).options(joinedload(WorkflowStage.role))
        if branch_id:
            stage_stmt = stage_stmt.where(WorkflowStage.branch_id == branch_id)
        stage_result = await db.execute(stage_stmt)
        stages = stage_result.scalars().all()
        stage_by_id = {s.stage_id: s for s in stages}
        expected_seq = sorted(
            [(s.stage_id, s.sequence_order or 9999, s.stage_code, s.stage_name) for s in stages],
            key=lambda x: x[1],
        )

        event_stmt = (
            select(CaptureEvent, WorkflowStage, Vehicle, JobCard)
            .outerjoin(WorkflowStage, CaptureEvent.stage_id == WorkflowStage.stage_id)
            .outerjoin(Vehicle, CaptureEvent.vehicle_id == Vehicle.vehicle_id)
            .outerjoin(JobCard, CaptureEvent.job_card_id == JobCard.job_card_id)
            .where(
                CaptureEvent.received_at_server >= start_dt,
                CaptureEvent.received_at_server < end_dt,
                CaptureEvent.voided == False,
            )
            .where(
                or_(
                    CaptureEvent.job_card_id.is_(None),
                    JobCard.status.notin_(["CANCELLED", "ZERO_BILLED"]),
                )
            )
            .order_by(CaptureEvent.received_at_server)
        )
        if branch_id:
            event_stmt = event_stmt.where(WorkflowStage.branch_id == branch_id)
        result = await db.execute(event_stmt)
        rows = result.all()

        flow_counts: Dict[int, dict] = {
            s.stage_id: {
                "stage_id": s.stage_id,
                "stage_code": s.stage_code,
                "stage_name": s.stage_name,
                "sequence_order": s.sequence_order,
                "role_name": s.role.role_name if s.role else None,
                "vehicles": set(),
                "capture_count": 0,
                "total_wait_minutes": 0.0,
                "wait_samples": 0,
                "max_wait_minutes": 0.0,
                "vehicle_max_wait": {},
            }
            for s in stages
        }

        vehicle_first_seen: Dict[Any, datetime] = {}
        for event, stage, vehicle, job_card in rows:
            if not stage:
                continue
            key = job_card.job_card_id if job_card else (vehicle.vehicle_id if vehicle else (event.plate_text_normalized or event.plate_text_raw or event.event_id))
            flow_counts[stage.stage_id]["vehicles"].add(key)
            flow_counts[stage.stage_id]["capture_count"] += 1
            now = event.received_at_server
            if key not in vehicle_first_seen:
                vehicle_first_seen[key] = now
            else:
                wait = (now - vehicle_first_seen[key]).total_seconds() / 60.0
                if wait > 0:
                    flow_counts[stage.stage_id]["total_wait_minutes"] += wait
                    flow_counts[stage.stage_id]["wait_samples"] += 1
                    current_max = flow_counts[stage.stage_id]["vehicle_max_wait"].get(key, 0.0)
                    if wait > current_max:
                        flow_counts[stage.stage_id]["vehicle_max_wait"][key] = wait
                    if wait > flow_counts[stage.stage_id]["max_wait_minutes"]:
                        flow_counts[stage.stage_id]["max_wait_minutes"] = wait

        stage_nodes = []
        for _, _, code, _ in expected_seq:
            stage = next((s for s in stages if s.stage_code == code), None)
            if not stage:
                continue
            data = flow_counts[stage.stage_id]
            samples = data["wait_samples"] or 1
            avg_wait = data["total_wait_minutes"] / max(1, samples)
            stage_nodes.append({
                "stage_id": data["stage_id"],
                "stage_code": data["stage_code"],
                "stage_name": data["stage_name"],
                "sequence_order": data["sequence_order"],
                "role_name": data["role_name"],
                "vehicle_count": len(data["vehicles"]),
                "capture_count": data["capture_count"],
                "avg_wait_minutes": round(avg_wait, 1),
                "max_wait_minutes": round(data["max_wait_minutes"], 1),
                "deviation_count": 0,
            })

        # Deviation counts across the full datetime range.
        from app.services.deviation_report_service import build_deviation_report_range
        deviation_report = await build_deviation_report_range(
            db, start_dt, end_dt, branch_id=branch_id
        )
        at_risk_alerts = await _AtRiskAlertService.live_alerts(db, branch_id)

        # Count deviations per stage_id from the report.
        stage_deviation_counts: Dict[int, int] = defaultdict(int)
        for dev in deviation_report.get("deviations", []):
            sid = dev.get("stage_id")
            if sid:
                stage_deviation_counts[sid] += 1

        for node in stage_nodes:
            node["deviation_count"] = stage_deviation_counts.get(node["stage_id"], 0)

        # Bottleneck rule: highest avg wait among stages with >0 captures.
        candidates = [n for n in stage_nodes if n["capture_count"] > 0]
        worst_bottleneck = None
        if candidates:
            worst = max(candidates, key=lambda n: n["avg_wait_minutes"])
            worst_bottleneck = {
                "stage_id": worst["stage_id"],
                "stage_code": worst["stage_code"],
                "stage_name": worst["stage_name"],
                "avg_wait_minutes": worst["avg_wait_minutes"],
                "vehicle_count": worst["vehicle_count"],
                "reason": "Highest average time since first entry in the selected window.",
            }

        return {
            "period_start": start_dt.isoformat(),
            "period_end": end_dt.isoformat(),
            "branch_id": branch_id,
            "stages": stage_nodes,
            "worst_bottleneck": worst_bottleneck,
            "at_risk_alerts": at_risk_alerts,
            "deviation_summary_note": (
                f"Total deviations {deviation_report['summary']['total_deviations']} "
                f"across {deviation_report['summary']['vehicles_with_deviations']} vehicles "
                f"in the selected window. See /dashboard/morning-meeting-deviations for details."
            ),
            "_deviation_summary": deviation_report["summary"],
        }


class _AtRiskAlertService:
    """Flag vehicles whose cycles are currently exceeding FRT target time."""

    @classmethod
    async def live_alerts(
        cls,
        db: AsyncSession,
        branch_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        from app.services.technician_time_service import _TechnicianTimeService

        # Find open job cards with target times.
        stmt = (
            select(JobCard, Vehicle)
            .outerjoin(Vehicle, JobCard.vehicle_id == Vehicle.vehicle_id)
            .where(JobCard.status.notin_(["CLOSED", "COMPLETED", "CANCELLED", "ZERO_BILLED"]))
        )
        if branch_id:
            stmt = stmt.where(JobCard.branch_id == branch_id)
        result = await db.execute(stmt)
        rows = result.all()

        alerts = []
        for job_card, vehicle in rows:
            report = await _TechnicianTimeService.build_report(db, job_card.job_card_id)
            if not report:
                continue
            target = report.get("total_target_time_minutes")
            if not target:
                continue
            total_work = sum((c.get("net_work_minutes") or 0) for c in report.get("cycles", []))
            if total_work <= target:
                continue
            alerts.append({
                "job_card_id": job_card.job_card_id,
                "external_job_card_no": job_card.external_job_card_no,
                "registration_number": vehicle.registration_number if vehicle else None,
                "stage_code": None,
                "stage_name": None,
                "target_minutes": target,
                "actual_minutes": round(total_work, 2),
                "excess_minutes": round(total_work - target, 2),
            })
        return sorted(alerts, key=lambda a: a["excess_minutes"], reverse=True)


class _PartsShortageService:
    """Aggregate parts_wait remarks to surface repeat shortage patterns."""

    @classmethod
    async def patterns(
        cls,
        db: AsyncSession,
        start_dt: datetime,
        end_dt: datetime,
        branch_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        stmt = (
            select(CaptureEvent)
            .options(joinedload(CaptureEvent.stage), joinedload(CaptureEvent.user))
            .where(
                CaptureEvent.parts_wait == True,
                CaptureEvent.received_at_server >= start_dt,
                CaptureEvent.received_at_server < end_dt,
                CaptureEvent.voided == False,
            )
        )
        if branch_id and hasattr(CaptureEvent, "branch_id"):
            stmt = stmt.where(CaptureEvent.branch_id == branch_id)
        result = await db.execute(stmt)
        events = result.scalars().all()

        # Naive normalisation: uppercase, strip leading 'PART(S)', collapse spaces.
        buckets: Dict[str, dict] = {}
        for ev in events:
            raw = ev.parts_wait_remark or ev.remarks or "NO_REMARK"
            key = cls._normalise(raw)
            bucket = buckets.setdefault(key, {
                "pattern_key": key,
                "sample_remarks": [],
                "occurrences": 0,
                "total_wait_minutes": 0.0,
                "job_card_ids": set(),
            })
            bucket["occurrences"] += 1
            bucket["job_card_ids"].add(ev.job_card_id)
            if len(bucket["sample_remarks"]) < 5:
                bucket["sample_remarks"].append(raw)

        # Supplement with Part E cycle wait time per pattern key.
        # Simplification: total parts wait across matched job cards.
        total_parts_wait_minutes = 0.0
        for key, bucket in buckets.items():
            wait = await cls._estimate_wait_for_job_cards(
                db, list(bucket["job_card_ids"])
            )
            total_parts_wait_minutes += wait
            bucket["total_wait_minutes"] = wait
            bucket["unique_job_cards"] = len(bucket["job_card_ids"])
            bucket["job_card_ids"] = list(bucket["job_card_ids"])

        top_patterns = []
        for bucket in sorted(buckets.values(), key=lambda b: b["occurrences"], reverse=True)[:20]:
            top_patterns.append({
                "pattern_key": bucket["pattern_key"],
                "count": bucket["occurrences"],
                "total_wait_minutes": bucket["total_wait_minutes"],
                "sample_remarks": bucket["sample_remarks"],
            })

        return {
            "period_start": start_dt.isoformat(),
            "period_end": end_dt.isoformat(),
            "branch_id": branch_id,
            "total_parts_wait_events": len(events),
            "total_parts_wait_minutes": round(total_parts_wait_minutes, 2),
            "top_patterns": top_patterns,
        }

    @classmethod
    def _normalise(cls, text: str) -> str:
        import re
        t = text.upper().strip()
        t = re.sub(r"^PARTS?\\s*[-:]?\\s*", "", t)
        t = re.sub(r"[^A-Z0-9]", " ", t)
        t = re.sub(r"\\s+", " ", t).strip()
        return t or "NO_REMARK"

    @classmethod
    async def _estimate_wait_for_job_cards(cls, db: AsyncSession, job_card_ids: List[int]) -> float:
        from app.services.technician_time_service import _TechnicianTimeService
        total = 0.0
        for jcid in job_card_ids:
            report = await _TechnicianTimeService.build_report(db, jcid)
            if report:
                total += report.get("total_parts_wait_minutes", 0.0)
        return round(total, 2)


class _StaffUtilizationService:
    """Active time vs shift time per staff member."""

    @classmethod
    async def utilization_by_day(
        cls,
        db: AsyncSession,
        target_date: date,
        branch_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        start = datetime.combine(target_date, datetime.min.time())
        end = start + timedelta(days=1)

        shift_stmt = select(UserShift, User, Role).outerjoin(User, UserShift.user_id == User.user_id).outerjoin(Role, User.role_id == Role.role_id)
        if branch_id:
            shift_stmt = shift_stmt.where(UserShift.branch_id == branch_id)
        shift_result = await db.execute(shift_stmt.where(UserShift.shift_date == target_date))
        shifts = shift_result.all()

        # Active time = first capture to last capture by user in this day.
        event_stmt = (
            select(
                CaptureEvent.user_id,
                func.min(CaptureEvent.received_at_server).label("first_capture"),
                func.max(CaptureEvent.received_at_server).label("last_capture"),
                func.count(CaptureEvent.event_id).label("capture_count"),
            )
            .where(
                CaptureEvent.received_at_server >= start,
                CaptureEvent.received_at_server < end,
                CaptureEvent.voided == False,
            )
            .group_by(CaptureEvent.user_id)
        )
        event_result = await db.execute(event_stmt)
        active_time = {row.user_id: row for row in event_result.all()}

        results = []
        for shift, user, role in shifts:
            shift_minutes = (shift.shift_end - shift.shift_start).total_seconds() / 60.0 - shift.break_minutes
            act = active_time.get(shift.user_id)
            active_minutes = 0.0
            captures = 0
            if act and act.first_capture and act.last_capture:
                active_minutes = max(0.0, (act.last_capture - act.first_capture).total_seconds() / 60.0)
                captures = act.capture_count
            results.append({
                "user_id": shift.user_id,
                "name": user.name if user else None,
                "role_name": role.role_name if role else None,
                "shift_date": shift.shift_date.isoformat(),
                "shift_start": shift.shift_start.isoformat(),
                "shift_end": shift.shift_end.isoformat(),
                "shift_minutes": round((shift.shift_end - shift.shift_start).total_seconds() / 60.0, 1),
                "break_minutes": shift.break_minutes,
                "available_minutes": round(shift_minutes, 1),
                "active_technician_minutes": round(active_minutes, 1),
                "utilization_percent": round(active_minutes / shift_minutes * 100, 1) if shift_minutes else 0.0,
                "capture_count": captures,
            })
        return results


class _ReworkRateReportService:
    """Surface rework-cycle counts per technician as a quality metric."""

    @classmethod
    async def report(
        cls,
        db: AsyncSession,
        start_dt: datetime,
        end_dt: datetime,
        branch_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        event_stmt = (
            select(CaptureEvent)
            .options(joinedload(CaptureEvent.user).joinedload(User.role))
            .where(
                CaptureEvent.received_at_server >= start_dt,
                CaptureEvent.received_at_server < end_dt,
                CaptureEvent.voided == False,
            )
            .where(
                or_(
                    CaptureEvent.job_card_id.is_(None),
                    JobCard.status.notin_(["CANCELLED", "ZERO_BILLED"]),
                )
            )
            .outerjoin(JobCard, CaptureEvent.job_card_id == JobCard.job_card_id)
        )
        if branch_id and hasattr(CaptureEvent, "branch_id"):
            event_stmt = event_stmt.where(CaptureEvent.branch_id == branch_id)
        result = await db.execute(event_stmt)
        events = result.scalars().unique().all()

        technician_rework: Dict[int, dict] = {}
        job_card_work_started_indices: Dict[int, List[int]] = defaultdict(list)
        for ev in events:
            if not ev.job_card_id:
                continue
            code = (ev.stage.stage_code or "").upper() if ev.stage else ""
            if code == "WORK_STARTED":
                job_card_work_started_indices[ev.job_card_id].append(ev.event_id)

        # Use technician_time_service cycles for correct per-technician rework attribution.
        from app.services.technician_time_service import _TechnicianTimeService
        for jcid in job_card_work_started_indices.keys():
            report = await _TechnicianTimeService.build_report(db, jcid)
            if not report:
                continue
            for idx, cycle in enumerate(report.get("cycles", [])):
                tech_id = cycle.get("technician_id")
                if not tech_id:
                    continue
                entry = technician_rework.setdefault(tech_id, {
                    "user_id": tech_id,
                    "user_name": cycle.get("technician_name"),
                    "total_cycles": 0,
                    "rework_cycles": 0,
                })
                entry["total_cycles"] += 1
                if idx > 0:
                    entry["rework_cycles"] += 1

        rows = sorted(technician_rework.values(), key=lambda x: x["rework_cycles"], reverse=True)
        technicians = [
            {
                "user_id": r["user_id"],
                "name": r["user_name"],
                "rework_cycles": r["rework_cycles"],
                "total_cycles": r["total_cycles"],
                "rework_rate_percent": round(r["rework_cycles"] / r["total_cycles"] * 100, 1) if r["total_cycles"] else 0.0,
            }
            for r in rows
        ]
        total_rework_cycles = sum(t["rework_cycles"] for t in technicians)
        return {
            "period_start": start_dt.isoformat(),
            "period_end": end_dt.isoformat(),
            "branch_id": branch_id,
            "total_rework_cycles": total_rework_cycles,
            "by_technician": technicians,
        }
