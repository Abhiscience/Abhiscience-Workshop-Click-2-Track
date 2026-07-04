"""Cancelled jobs with partial work — manager-only accountability report."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from collections import defaultdict
from datetime import datetime

from app.models.models import JobCard, CaptureEvent, User, WorkflowStage, Vehicle, CancellationCategory


class _CancelledPartialWorkReportBuilder:
    """Build the cancelled-with-partial-work report.

    This report deliberately does not attribute work to technicians for
    performance/productivity purposes; it exists only to show managers that
    labour was expended before a job was cancelled.
    """

    @classmethod
    async def build(
        cls,
        db: AsyncSession,
        *,
        branch_id: int | None = None,
        cancellation_category_id: int | None = None,
    ):
        stmt = (
            select(JobCard)
            .options(
                joinedload(JobCard.vehicle),
                joinedload(JobCard.cancellation_category),
            )
            .where(JobCard.status == "CANCELLED")
        )
        if branch_id:
            stmt = stmt.where(JobCard.branch_id == branch_id)
        if cancellation_category_id:
            stmt = stmt.where(JobCard.cancellation_category_id == cancellation_category_id)
        stmt = stmt.order_by(JobCard.close_time.desc())

        result = await db.execute(stmt)
        cancelled_cards = result.unique().scalars().all()

        items = []
        for jc in cancelled_cards:
            # load capture events for this job card (non-voided only)
            event_result = await db.execute(
                select(CaptureEvent)
                .options(
                    joinedload(CaptureEvent.stage),
                    joinedload(CaptureEvent.user).joinedload(User.role),
                )
                .where(
                    CaptureEvent.job_card_id == jc.job_card_id,
                    CaptureEvent.voided == False,
                )
                .order_by(CaptureEvent.received_at_server)
            )
            events = event_result.scalars().all()

            if not events:
                continue  # only include jobs that had real capture work done

            by_user: dict[int, dict] = defaultdict(lambda: {
                "user_id": None,
                "user_name": "Unknown",
                "role_name": None,
                "events": [],
                "event_count": 0,
                "total_time_minutes": 0.0,
            })

            prev_at: datetime | None = None
            total_capture_time = 0.0

            for e in events:
                user = e.user
                uid = user.user_id if user else 0
                bucket = by_user[uid]
                bucket["user_id"] = uid
                bucket["user_name"] = user.name if user else "Unknown"
                bucket["role_name"] = user.role.role_name if user and user.role else None

                captured_at = e.received_at_server or e.captured_at_device
                # time logged = duration from previous capture by same user, capped at 120 min
                time_minutes = 0.0
                if prev_at and captured_at:
                    delta = (captured_at - prev_at).total_seconds() / 60.0
                    if 0 < delta <= 120:
                        time_minutes = delta
                prev_at = captured_at

                bucket["events"].append({
                    "event_id": e.event_id,
                    "stage_id": e.stage_id,
                    "stage_name": e.stage.stage_name if e.stage else None,
                    "stage_code": e.stage.stage_code if e.stage else None,
                    "user_id": uid,
                    "user_name": bucket["user_name"],
                    "role_name": bucket["role_name"],
                    "captured_at": captured_at,
                    "time_logged_minutes": round(time_minutes, 2),
                    "remarks": e.remarks,
                })
                bucket["event_count"] += 1
                bucket["total_time_minutes"] += time_minutes
                total_capture_time += time_minutes

            technician_summary = []
            for bucket in by_user.values():
                technician_summary.append({
                    "user_id": bucket["user_id"],
                    "user_name": bucket["user_name"],
                    "role_name": bucket["role_name"],
                    "event_count": bucket["event_count"],
                    "total_time_minutes": round(bucket["total_time_minutes"], 2),
                    "events": bucket["events"],
                })

            cancel_event_result = await db.execute(
                select(CaptureEvent.user_id)
                .where(
                    CaptureEvent.job_card_id == jc.job_card_id,
                    CaptureEvent.voided == False,
                )
                .order_by(CaptureEvent.received_at_server.desc())
                .limit(1)
            )
            cancelled_by = cancel_event_result.scalar() or jc.advisor_id
            cancelled_by_name = None
            if cancelled_by:
                u = await db.execute(select(User).where(User.user_id == cancelled_by))
                user = u.scalar_one_or_none()
                cancelled_by_name = user.name if user else None

            items.append({
                "job_card_id": jc.job_card_id,
                "external_job_card_no": jc.external_job_card_no,
                "registration_number": jc.vehicle.registration_number if jc.vehicle else None,
                "vehicle_id": jc.vehicle_id,
                "branch_id": jc.branch_id,
                "cancellation_category_id": jc.cancellation_category_id,
                "cancellation_category_name": jc.cancellation_category.category_name if jc.cancellation_category else None,
                "cancellation_reason": jc.cancellation_reason,
                "cancelled_at": jc.close_time,
                "cancelled_by": cancelled_by,
                "cancelled_by_name": cancelled_by_name,
                "technician_summary": technician_summary,
                "total_capture_time_minutes": round(total_capture_time, 2),
                "event_count": len(events),
            })

        return items
