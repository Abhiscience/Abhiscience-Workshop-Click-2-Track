"""Admin management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
import re
from datetime import datetime

from app.providers.ocr_provider import get_ocr_provider
from app.core.security import decode_token, get_password_hash
from app.core.database import get_db
from app.models.models import Branch, CaptureEvent, JobCard, JobCategory, Role, User, Vehicle, WorkflowStage

router = APIRouter()

async def get_admin_user():
    return {"user_id": "1"}


@router.get("/dashboard/branch-overview")
async def get_branch_overview(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get branch overview with real counts."""
    branch_stmt = select(Branch)
    branch_result = await db.execute(branch_stmt)
    branches = branch_result.scalars().all()

    branch_data = []
    for branch in branches:
        user_count_result = await db.execute(
            select(func.count(User.user_id)).where(User.branch_id == branch.branch_id)
        )
        user_count = user_count_result.scalar() or 0

        job_count_result = await db.execute(
            select(func.count(JobCard.job_card_id)).where(
                JobCard.branch_id == branch.branch_id,
                JobCard.status.in_(["OPEN", "IN_PROGRESS"])
            )
        )
        active_job_count = job_count_result.scalar() or 0

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        capture_count_result = await db.execute(
            select(func.count(CaptureEvent.event_id))
            .outerjoin(WorkflowStage, CaptureEvent.stage_id == WorkflowStage.stage_id)
            .where(
                WorkflowStage.branch_id == branch.branch_id,
                CaptureEvent.received_at_server >= today_start
            )
        )
        capture_count = capture_count_result.scalar() or 0

        branch_data.append({
            "branch_id": branch.branch_id,
            "branch_name": branch.branch_name,
            "timezone": branch.timezone,
            "user_count": user_count,
            "active_job_cards": active_job_count,
            "today_captures": capture_count,
        })

    total_vehicles_result = await db.execute(select(func.count(Vehicle.vehicle_id)))
    total_vehicles = total_vehicles_result.scalar() or 0

    return {
        "branches": branch_data,
        "total_vehicles": total_vehicles,
        "utilization_rate": 0
    }


@router.get("/workflow-stages")
async def get_workflow_stages(
    branch_id: int = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workflow stage configuration."""
    from sqlalchemy.orm import selectinload

    stmt = select(WorkflowStage).options(selectinload(WorkflowStage.role))
    if branch_id:
        stmt = stmt.where(WorkflowStage.branch_id == branch_id)
    stmt = stmt.order_by(WorkflowStage.sequence_order)
    result = await db.execute(stmt)
    stages = result.scalars().all()

    return {
        "stages": [
            {
                "stage_id": s.stage_id,
                "branch_id": s.branch_id,
                "stage_code": s.stage_code,
                "stage_name": s.stage_name,
                "sequence_order": s.sequence_order,
                "capture_mandatory": s.capture_mandatory,
                "role_id": s.role_id,
                "role_name": s.role.role_name if s.role else None,
            }
            for s in stages
        ]
    }


@router.post("/workflow-stages")
async def create_workflow_stage(
    stage_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new workflow stage."""
    stage = WorkflowStage(
        branch_id=stage_data.get("branch_id"),
        stage_code=stage_data.get("stage_code"),
        stage_name=stage_data.get("stage_name"),
        sequence_order=stage_data.get("sequence_order"),
        capture_mandatory=stage_data.get("capture_mandatory", True),
        role_id=stage_data.get("role_id"),
    )
    db.add(stage)
    try:
        await db.commit()
        await db.refresh(stage)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Stage could not be created")

    # optionally resolve role
    role = None
    if stage.role_id:
        role = await db.get(Role, stage.role_id)

    return {
        "status": "created",
        "stage": {
            "stage_id": stage.stage_id,
            "branch_id": stage.branch_id,
            "stage_code": stage.stage_code,
            "stage_name": stage.stage_name,
            "sequence_order": stage.sequence_order,
            "capture_mandatory": stage.capture_mandatory,
            "role_id": stage.role_id,
            "role_name": role.role_name if role else None,
        }
    }


@router.get("/users")
async def list_users(
    branch_id: int = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users."""
    stmt = select(User)
    if branch_id:
        stmt = stmt.where(User.branch_id == branch_id)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return {
        "users": [
            {
                "user_id": u.user_id,
                "name": u.name,
                "mobile": u.mobile,
                "role_id": u.role_id,
                "branch_id": u.branch_id,
                "status": u.status,
            }
            for u in users
        ]
    }


@router.post("/users")
async def create_user(
    user_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new user with hashed password."""
    required = ["name", "mobile", "role_id", "branch_id", "password"]
    missing = [f for f in required if f not in user_data or not user_data[f]]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {', '.join(missing)}")

    existing = await db.execute(select(User).where(User.mobile == user_data["mobile"]))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="User with this mobile already exists")

    user = User(
        name=user_data["name"],
        mobile=user_data["mobile"],
        role_id=user_data["role_id"],
        branch_id=user_data["branch_id"],
        status=user_data.get("status", "ACTIVE"),
        password_hash=get_password_hash(user_data["password"]),
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="User could not be created")

    return {
        "status": "created",
        "user": {
            "user_id": user.user_id,
            "name": user.name,
            "mobile": user.mobile,
            "role_id": user.role_id,
            "branch_id": user.branch_id,
            "status": user.status,
        }
    }


@router.get("/audit-trail")
async def get_audit_trail(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """View audit trail of recent capture events."""
    stmt = (
        select(CaptureEvent, User, WorkflowStage)
        .outerjoin(User, CaptureEvent.user_id == User.user_id)
        .outerjoin(WorkflowStage, CaptureEvent.stage_id == WorkflowStage.stage_id)
        .order_by(CaptureEvent.received_at_server.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "events": [
            {
                "event_id": e.event_id,
                "job_card_id": e.job_card_id,
                "vehicle_id": e.vehicle_id,
                "stage_code": ws.stage_code if ws else None,
                "stage_name": ws.stage_name if ws else None,
                "user_name": u.name if u else None,
                "captured_at_device": e.captured_at_device.isoformat() if e.captured_at_device else None,
                "received_at_server": e.received_at_server.isoformat() if e.received_at_server else None,
                "plate_text_raw": e.plate_text_raw,
                "match_status": e.match_status.value if hasattr(e.match_status, 'value') else e.match_status,
                "image_url": e.image_url,
                "remarks": e.remarks,
            }
            for e, u, ws in rows
        ]
    }


def _parse_plate(raw: str) -> dict:
    text = re.sub(r'[^A-Z0-9]', '', raw.upper())
    if re.match(r'^[A-Z]{2}[0-9]{2}[A-Z]{1,3}[0-9]{1,4}$', text):
        return {"format_type": "indian", "region_code": text[:2], "plate_number": text[2:], "normalized": text, "confidence": 0.95, "raw_text": raw}
    m = re.match(r'^([A-Z]{1,2})([0-9]{1,5})$', text)
    if m:
        return {"format_type": "uae", "region_code": m.group(1), "plate_number": m.group(2), "normalized": text, "confidence": 0.93, "raw_text": raw}
    if re.match(r'^[0-9]{1,5}$', text):
        return {"format_type": "uae", "region_code": None, "plate_number": text, "normalized": text, "confidence": 0.95, "raw_text": raw}
    numbers = re.sub(r'[^0-9]', '', text)
    if len(numbers) >= 4:
        return {"format_type": "uae", "region_code": None, "plate_number": numbers, "normalized": numbers, "confidence": 0.85, "raw_text": raw}
    return {"format_type": "unknown", "region_code": None, "plate_number": text, "normalized": text, "confidence": 0.50, "raw_text": raw}


@router.post("/plate-ocr")
async def plate_ocr(file: UploadFile = File(...)):
    """OCR endpoint for license plates using OCR.space."""
    contents = await file.read()
    provider = get_ocr_provider()
    result = await provider.recognize_plate(contents, file.filename or "upload.jpg")
    if not result.get("success") or not result.get("plate_text_raw"):
        raise HTTPException(status_code=422, detail=result.get("error", "No license plate detected"))
    return _parse_plate(result["plate_text_raw"])



@router.get("/roles")
async def list_roles(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List all roles."""
    result = await db.execute(select(Role).order_by(Role.role_name))
    roles = result.scalars().all()
    return {
        "roles": [
            {
                "role_id": r.role_id,
                "role_name": r.role_name,
                "capture_label": r.capture_label,
                "permissions": r.permissions,
            }
            for r in roles
        ]
    }


@router.post("/roles")
async def create_role(
    role_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new role."""
    if not role_data.get("role_name"):
        raise HTTPException(status_code=400, detail="role_name is required")
    existing = await db.execute(select(Role).where(Role.role_name == role_data["role_name"]))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Role already exists")

    role = Role(
        role_name=role_data["role_name"],
        capture_label=role_data.get("capture_label"),
        permissions=role_data.get("permissions", {}),
    )
    db.add(role)
    try:
        await db.commit()
        await db.refresh(role)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Role could not be created")

    return {
        "status": "created",
        "role": {
            "role_id": role.role_id,
            "role_name": role.role_name,
            "capture_label": role.capture_label,
            "permissions": role.permissions,
        }
    }


@router.get("/job-categories")
async def list_job_categories(
    branch_id: int = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List job categories for dropdown."""
    stmt = select(JobCategory)
    if branch_id:
        stmt = stmt.where(
            (JobCategory.branch_id == branch_id) | (JobCategory.branch_id.is_(None))
        )
    stmt = stmt.where(JobCategory.is_active == True).order_by(JobCategory.category_name)
    result = await db.execute(stmt)
    categories = result.scalars().all()
    return {
        "categories": [
            {
                "job_category_id": c.job_category_id,
                "branch_id": c.branch_id,
                "category_name": c.category_name,
                "category_code": c.category_code,
                "is_active": c.is_active,
            }
            for c in categories
        ]
    }


@router.post("/job-categories")
async def create_job_category(
    category_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new job category."""
    if not category_data.get("category_name"):
        raise HTTPException(status_code=400, detail="category_name is required")
    category = JobCategory(
        branch_id=category_data.get("branch_id"),
        category_name=category_data["category_name"],
        category_code=category_data.get("category_code"),
        is_active=category_data.get("is_active", True),
    )
    db.add(category)
    try:
        await db.commit()
        await db.refresh(category)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Category could not be created")

    return {
        "status": "created",
        "category": {
            "job_category_id": category.job_category_id,
            "branch_id": category.branch_id,
            "category_name": category.category_name,
            "category_code": category.category_code,
            "is_active": category.is_active,
        }
    }

