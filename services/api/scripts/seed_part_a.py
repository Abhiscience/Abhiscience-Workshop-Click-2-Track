"""Idempotent seed for Part A: roles and workflow stages for branch 3.

Run from services/api with:
    PYTHONPATH=/root/Abhiscience-Workshop-Click-2-Track/services/api/app python3 scripts/seed_part_a.py

Or from inside the API venv:
    cd /root/Abhiscience-Workshop-Click-2-Track/services/api
    .venv/bin/python3 scripts/seed_part_a.py
"""
import asyncio
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import async_session, init_db
from app.models.models import Role, Branch, WorkflowStage


ROLES = [
    {"role_id": 1, "role_name": "SECURITY_GUARD", "capture_label": "Captured by Security Guard", "permissions": {"capture": True, "view_timeline": False}},
    {"role_id": 2, "role_name": "SERVICE_ADVISOR", "capture_label": "Captured by Advisor", "permissions": {"capture": True, "create_jc": True, "view_timeline": True}},
    {"role_id": 3, "role_name": "TECHNICIAN", "capture_label": "Captured by Technician", "permissions": {"capture": True, "update_status": True, "view_timeline": True}},
    {"role_id": 4, "role_name": "WASHER", "capture_label": "Captured by Washer", "permissions": {"capture": True, "view_timeline": True}},
    {"role_id": 5, "role_name": "PARTS_MANAGER", "capture_label": "Captured by Parts Manager", "permissions": {"capture": True, "issue_parts": True, "view_timeline": True}},
    {"role_id": 6, "role_name": "QUALITY_MANAGER", "capture_label": "Captured by QC Manager", "permissions": {"capture": True, "view_timeline": True}},
    {"role_id": 7, "role_name": "DELIVERY_COORDINATOR", "capture_label": "Captured by Delivery", "permissions": {"capture": True, "view_timeline": True}},
    {"role_id": 8, "role_name": "WORKSHOP_MANAGER", "capture_label": "Manager Action", "permissions": {"capture": False, "admin": True, "view_all": True}},
    {"role_id": 9, "role_name": "SYSTEM_ADMIN", "capture_label": "System Admin", "permissions": {"admin": True, "configure": True}},
    {"role_id": 10, "role_name": "BRANCH_ADMIN", "capture_label": "Branch Admin", "permissions": {"capture": False, "view_branch": True}},
    {"role_id": 11, "role_name": "FLOOR_INCHARGE", "capture_label": "Captured by Floor Incharge", "permissions": {"capture": True, "assign_technician": True, "view_timeline": True}},
]

STAGES = [
    ("SECURITY_GATE", "Security Gate Check", 1, "SECURITY_GUARD"),
    ("GATE_IN", "Gate In / Job Card Opened", 2, "SERVICE_ADVISOR"),
    ("TECH_ASSIGNED", "Assigned to Technician", 3, "FLOOR_INCHARGE"),
    ("WORK_STARTED", "Technician Starts Work", 4, "TECHNICIAN"),
    ("PARTS_ISSUED", "Parts Issued", 5, "PARTS_MANAGER"),
    ("WORK_FINISHED", "Technician Finishes Work", 6, "TECHNICIAN"),
    ("READY_FOR_QC", "Handoff to QC Queue", 7, "FLOOR_INCHARGE"),
    ("PRE_ROAD_TEST_QC", "Pre-Road-Test QC", 8, "QUALITY_MANAGER"),
    ("WASHING", "Washing", 9, "WASHER"),
    ("PRE_DELIVERY_CHECK", "Pre-Delivery Check", 10, "SERVICE_ADVISOR"),
]

BRANCH_ID = 3


async def seed():
    await init_db()
    async with async_session() as db:
        # Ensure branch exists
        branch = await db.execute(select(Branch).where(Branch.branch_id == BRANCH_ID))
        if not branch.scalar_one_or_none():
            db.add(Branch(branch_id=BRANCH_ID, branch_name="Main Branch", timezone="Asia/Dubai"))
            await db.commit()
            print(f"Created branch {BRANCH_ID}")

        # Upsert roles using fixed role_ids
        role_by_name = {}
        for r in ROLES:
            role = Role(**r)
            db.add(role)
            await db.commit()
            await db.refresh(role)
            role_by_name[r["role_name"]] = role.role_id
            print(f"Ensured role {r['role_name']} -> id {role.role_id}")

        # Idempotent upsert stages
        for stage_code, stage_name, seq, role_name in STAGES:
            role_id = role_by_name[role_name]
            existing = await db.execute(
                select(WorkflowStage).where(
                    WorkflowStage.branch_id == BRANCH_ID,
                    WorkflowStage.stage_code == stage_code,
                )
            )
            if existing.scalar_one_or_none():
                print(f"Stage {stage_code} already exists")
                continue
            stage = WorkflowStage(
                branch_id=BRANCH_ID,
                stage_code=stage_code,
                stage_name=stage_name,
                sequence_order=seq,
                capture_mandatory=True,
                role_id=role_id,
            )
            db.add(stage)
            await db.commit()
            await db.refresh(stage)
            print(f"Created stage {stage_code} (seq {seq}) -> role {role_name}")

        print("\nDone. Verify with: GET /api/v1/admin/workflow-stages?branch_id=3")


if __name__ == "__main__":
    asyncio.run(seed())
