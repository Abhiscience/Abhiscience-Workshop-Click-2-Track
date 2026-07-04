import asyncio
from datetime import datetime, timedelta
from app.core.database import async_session
from app.models.models import CaptureEvent, MatchStatus

async def seed():
    async with async_session() as db:
        now = datetime.utcnow()
        events = [
            # (stage_id, offset_minutes, user_id, remark)
            (7, 0, 10, "Cycle 1: Work started (Tech A)"),
            (9, 20, 10, "Cycle 1: Work finished (Tech A)"),
            (10, 22, 9, "Cycle 1: Ready for QC"),
            (11, 30, 9, "Cycle 1: QC FAILED"),
            (7, 35, 11, "Cycle 2: Rework started (Tech B)"),
            (9, 55, 11, "Cycle 2: Rework finished (Tech B)"),
            (10, 57, 9, "Cycle 2: Ready for QC"),
            (11, 65, 9, "Cycle 2: QC PASSED"),
        ]
        for stage_id, offset, user_id, remark in events:
            event = CaptureEvent(
                stage_id=stage_id,
                job_card_id=7,
                vehicle_id=7,
                user_id=user_id,
                installation_id=1,
                plate_text_raw="REWORKTEST",
                plate_text_normalized="REWORKTEST",
                plate_confidence=0.95,
                match_status=MatchStatus.EXACT_MATCH,
                captured_at_device=now + timedelta(minutes=offset),
                received_at_server=now + timedelta(minutes=offset),
                remarks=remark,
            )
            db.add(event)
        await db.commit()
        print("Rework test events created for job_card_id=7")

asyncio.run(seed())
