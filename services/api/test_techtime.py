import asyncio
from datetime import datetime, timedelta
from app.core.database import async_session
from app.models.models import CaptureEvent, MatchStatus

async def seed():
    async with async_session() as db:
        now = datetime.utcnow()
        events = [
            # (stage_id, offset_minutes, parts_wait, remark)
            (7, 0, False, "Work started"),      # WORK_STARTED
            (8, 10, True, "Waiting for brake pads"),  # PARTS_ISSUED, parts_wait=True
            (9, 40, False, "Work finished"),    # WORK_FINISHED
            (10, 42, False, "Ready for QC"),    # READY_FOR_QC
            (11, 70, False, "QC done"),         # PRE_ROAD_TEST_QC
        ]
        for stage_id, offset, parts_wait, remark in events:
            event = CaptureEvent(
                stage_id=stage_id,
                job_card_id=5,
                vehicle_id=5,
                user_id=10,
                installation_id=1,
                plate_text_raw="TECHTIMETEST",
                plate_text_normalized="TECHTIMETEST",
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
        print("Test events created for job_card_id=5")

asyncio.run(seed())
