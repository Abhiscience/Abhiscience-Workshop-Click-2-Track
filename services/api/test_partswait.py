import asyncio
from datetime import datetime, timedelta
from app.core.database import async_session
from app.models.models import CaptureEvent, MatchStatus

async def seed():
    async with async_session() as db:
        now = datetime.utcnow()
        events = [
            # (stage_id, offset_minutes, parts_wait, remark)
            (7, 0, False, "Work started"),                    # WORK_STARTED
            (8, 10, True, "Requesting brake pads"),            # PARTS_ISSUED, wait flagged
            (8, 15, False, "Part arrived, resuming"),          # PARTS_ISSUED again, wait resolved
            (9, 40, False, "Work finished"),                   # WORK_FINISHED
        ]
        for stage_id, offset, parts_wait, remark in events:
            event = CaptureEvent(
                stage_id=stage_id,
                job_card_id=6,
                vehicle_id=6,
                user_id=10,
                installation_id=1,
                plate_text_raw="TECHTIME2",
                plate_text_normalized="TECHTIME2",
                plate_confidence=0.95,
                match_status=MatchStatus.EXACT_MATCH,
                captured_at_device=now + timedelta(minutes=offset),
                received_at_server=now + timedelta(minutes=offset),
                remarks=remark,
                parts_wait=parts_wait,
                parts_wait_remark="Brake pads out of stock" if parts_wait else None,
            )
            db.add(event)
        await db.commit()
        print("Test events created for job_card_id=6")

asyncio.run(seed())

