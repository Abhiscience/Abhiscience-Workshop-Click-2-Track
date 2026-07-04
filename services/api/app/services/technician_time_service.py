"""Part E: technician time, QC wait, rework cycle calculation."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from datetime import datetime
from typing import List, Optional

from app.models.models import CaptureEvent, JobCard, User, WorkflowStage, Vehicle, JobCardJobType, FlatRateTimeCatalog


class _TechnicianTimeService:
    """Compute technician work cycles, parts-wait, and QC queue wait per job card.

    Cycle definition:
      - A cycle starts at WORK_STARTED for a technician.
      - It ends at the next WORK_FINISHED for that same technician OR at the
        next READY_FOR_QC, whichever comes first.
      - Rework: after PRE_ROAD_TEST_QC fails (marked by a rework capture at that
        stage or by a later WORK_STARTED), each new WORK_STARTED starts a new
        cycle attributed to the capturing technician.
      - Parts-wait: only PARTS_ISSUED with parts_wait=True contributes wait time
        within the cycle span and is subtracted from technician time.
      - QC wait: READY_FOR_QC → PRE_ROAD_TEST_QC, not attributed to any technician.
    """

    CYCLE_START = {"WORK_STARTED"}
    CYCLE_END = {"WORK_FINISHED", "READY_FOR_QC"}
    QC_READY = "READY_FOR_QC"
    QC_TEST = "PRE_ROAD_TEST_QC"
    PARTS_ISSUED = "PARTS_ISSUED"

    @classmethod
    async def build_report(cls, db: AsyncSession, job_card_id: int):
        jc_result = await db.execute(
            select(JobCard)
            .options(joinedload(JobCard.vehicle))
            .where(JobCard.job_card_id == job_card_id)
        )
        job_card = jc_result.scalar_one_or_none()
        if not job_card:
            return None

        events_result = await db.execute(
            select(CaptureEvent)
            .options(
                joinedload(CaptureEvent.stage),
                joinedload(CaptureEvent.user).joinedload(User.role),
            )
            .where(
                CaptureEvent.job_card_id == job_card_id,
                CaptureEvent.voided == False,
            )
            .order_by(CaptureEvent.received_at_server)
        )
        events = events_result.scalars().all()

        # Load target time
        target_time = await cls._target_time_for_job_card(db, job_card_id)

        cycles = cls._compute_cycles(events)
        qc_waits = cls._compute_qc_waits(events)
        total_parts_wait = sum(c["parts_wait_minutes"] for c in cycles)

        return {
            "job_card_id": job_card.job_card_id,
            "external_job_card_no": job_card.external_job_card_no,
            "registration_number": job_card.vehicle.registration_number if job_card.vehicle else None,
            "total_target_time_minutes": target_time,
            "cycles": cycles,
            "qc_wait_windows": qc_waits,
            "total_parts_wait_minutes": round(total_parts_wait, 2),
        }

    @classmethod
    async def _target_time_for_job_card(cls, db: AsyncSession, job_card_id: int) -> Optional[int]:
        result = await db.execute(
            select(JobCardJobType, FlatRateTimeCatalog)
            .join(FlatRateTimeCatalog, JobCardJobType.frt_entry_id == FlatRateTimeCatalog.frt_entry_id)
            .where(JobCardJobType.job_card_id == job_card_id)
        )
        total = 0
        rows = result.all()
        if not rows:
            return None
        for _, frt in rows:
            total += frt.target_time_minutes or 0
        return total

    @classmethod
    def _event_ts(cls, event) -> Optional[datetime]:
        return event.received_at_server or event.captured_at_device

    @classmethod
    def _stage_code(cls, event) -> str:
        return (event.stage.stage_code or "").upper() if event.stage else ""

    @classmethod
    def _stage_event_dict(cls, event) -> dict:
        user = event.user
        stage = event.stage
        return {
            "event_id": event.event_id,
            "stage_code": cls._stage_code(event),
            "stage_name": stage.stage_name if stage else None,
            "user_id": user.user_id if user else None,
            "user_name": user.name if user else None,
            "role_name": user.role.role_name if user and user.role else None,
            "captured_at": cls._event_ts(event),
            "parts_wait": event.parts_wait,
            "parts_wait_remark": event.parts_wait_remark,
        }

    @classmethod
    def _compute_cycles(cls, events: List[CaptureEvent]) -> List[dict]:
        cycles = []
        current_cycle = None

        for event in events:
            code = cls._stage_code(event)
            ts = cls._event_ts(event)

            if code in cls.CYCLE_START:
                # Close any open cycle if another WORK_STARTED appears before closure.
                if current_cycle is not None:
                    # Use current event time as forced end boundary
                    current_cycle["finished_at"] = ts
                    current_cycle["total_minutes"] = cls._minutes_between(
                        current_cycle["started_at"], ts
                    )
                    cls._finalize_cycle(current_cycle)
                    cycles.append(current_cycle)

                current_cycle = {
                    "cycle_number": len(cycles) + 1,
                    "started_at": ts,
                    "finished_at": None,
                    "technician_id": event.user_id,
                    "technician_name": event.user.name if event.user else None,
                    "total_minutes": 0.0,
                    "parts_wait_minutes": 0.0,
                    "net_work_minutes": 0.0,
                    "stage_events": [cls._stage_event_dict(event)],
                    "_parts_wait_start": None,
                }
                continue

            if current_cycle is None:
                continue

            current_cycle["stage_events"].append(cls._stage_event_dict(event))

            if code == cls.PARTS_ISSUED and event.parts_wait:
                # Begin tracking parts-wait window
                if not current_cycle["_parts_wait_start"]:
                    current_cycle["_parts_wait_start"] = ts
            elif current_cycle["_parts_wait_start"]:
                # End parts-wait window at the next non-parts-wait event
                delta = cls._minutes_between(current_cycle["_parts_wait_start"], ts)
                if delta > 0:
                    current_cycle["parts_wait_minutes"] += delta
                current_cycle["_parts_wait_start"] = None

            if code in cls.CYCLE_END and current_cycle:
                current_cycle["finished_at"] = ts
                current_cycle["total_minutes"] = cls._minutes_between(
                    current_cycle["started_at"], ts
                )
                cls._finalize_cycle(current_cycle)
                cycles.append(current_cycle)
                current_cycle = None

        # Handle last cycle without explicit end
        if current_cycle is not None:
            last_ts = cls._event_ts(events[-1]) if events else None
            if current_cycle["_parts_wait_start"] and last_ts:
                delta = cls._minutes_between(current_cycle["_parts_wait_start"], last_ts)
                if delta > 0:
                    current_cycle["parts_wait_minutes"] += delta
            current_cycle["finished_at"] = None
            current_cycle["total_minutes"] = None
            cls._finalize_cycle(current_cycle)
            cycles.append(current_cycle)

        return cycles

    @classmethod
    def _finalize_cycle(cls, cycle: dict):
        if cycle["total_minutes"] is not None:
            cycle["net_work_minutes"] = round(
                max(0.0, cycle["total_minutes"] - cycle["parts_wait_minutes"]), 2
            )
            cycle["total_minutes"] = round(cycle["total_minutes"], 2)
        else:
            cycle["net_work_minutes"] = None
        cycle["parts_wait_minutes"] = round(cycle["parts_wait_minutes"], 2)
        # remove internal key
        cycle.pop("_parts_wait_start", None)

    @classmethod
    def _compute_qc_waits(cls, events: List[CaptureEvent]) -> List[dict]:
        windows = []
        ready_at = None
        for event in events:
            code = cls._stage_code(event)
            ts = cls._event_ts(event)
            if code == cls.QC_READY:
                ready_at = ts
            elif code == cls.QC_TEST and ready_at:
                windows.append({
                    "ready_for_qc_at": ready_at,
                    "pre_road_test_qc_at": ts,
                    "qc_wait_minutes": round(cls._minutes_between(ready_at, ts), 2),
                })
                ready_at = None
        return windows

    @classmethod
    def _minutes_between(cls, start: Optional[datetime], end: Optional[datetime]) -> float:
        if not start or not end or end <= start:
            return 0.0
        return (end - start).total_seconds() / 60.0
