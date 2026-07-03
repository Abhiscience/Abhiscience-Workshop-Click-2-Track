import asyncio
from datetime import datetime, timedelta
from app.core.database import async_session
from app.models.models import CaptureEvent, MatchStatus

async def seed():
    async with async_session() as db:
        now = datetime.utcnow()

        # Vehicle A: legitimate rework (Work Started -> QC -> Work Started again)
        events_a = [
            (7, 0, "REWORKGOOD"),   # WORK_STARTED
            (11, 30, "REWORKGOOD"), # PRE_ROAD_TEST_QC
            (7, 40, "REWORKGOOD"),  # WORK_STARTED again - legitimate rework
        ]

        # Vehicle B: genuine duplicate error (Work Started twice, no QC between)
        events_b = [
            (7, 0, "DUPLICATEBAD"),   # WORK_STARTED
            (7, 15, "DUPLICATEBAD"),  # WORK_STARTED again - NO QC in between, real error
        ]

        for stage_id, offset, plate in events_a + events_b:
            event = CaptureEvent(
                stage_id=stage_id,
                user_id=10,
                installation_id=1,
                plate_text_raw=plate,
                plate_text_normalized=plate,
                plate_confidence=0.95,
                match_status=MatchStatus.PENDING_NO_JC,
                captured_at_device=now + timedelta(minutes=offset),
                received_at_server=now + timedelta(minutes=offset),
                remarks=f"Part C test {plate}"
            )
            db.add(event)
        await db.commit()
        print("Test events created")

asyncio.run(seed())
