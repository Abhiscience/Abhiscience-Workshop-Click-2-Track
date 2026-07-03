"""Job-card not-applicable stage tracking (Part D).

A stage can be marked "not applicable" for a specific job card, with a required
reason. Such stages are treated as compliant in all compliance / deviation
calculations and are excluded from expected sequences for that job.
"""
from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import JobCardNotApplicableStage as NAModel


async def mark_stage_not_applicable(
    db: AsyncSession,
    job_card_id: int,
    stage_id: int,
    reason: str,
    marked_by_user_id: int,
) -> NAModel:
    if not reason or not reason.strip():
        raise ValueError("reason is required")

    existing = await get_not_applicable_stages(db, job_card_id=job_card_id, stage_id=stage_id)
    if existing:
        na = existing[0]
        na.reason = reason.strip()
        na.marked_by_user_id = marked_by_user_id
        na.marked_at = datetime.utcnow()
        await db.flush()
        return na

    na = NAModel(
        job_card_id=job_card_id,
        stage_id=stage_id,
        reason=reason.strip(),
        marked_by_user_id=marked_by_user_id,
    )
    db.add(na)
    await db.flush()
    return na


async def get_not_applicable_stages(
    db: AsyncSession,
    job_card_id: Optional[int] = None,
    stage_id: Optional[int] = None,
) -> List[NAModel]:
    stmt = select(NAModel)
    if job_card_id is not None:
        stmt = stmt.where(NAModel.job_card_id == job_card_id)
    if stage_id is not None:
        stmt = stmt.where(NAModel.stage_id == stage_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_not_applicable_stage_ids(
    db: AsyncSession,
    job_card_id: int,
) -> set:
    if not job_card_id:
        return set()
    stmt = select(NAModel.stage_id).where(NAModel.job_card_id == job_card_id)
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}
