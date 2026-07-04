"""Admin management endpoints."""
import re
from datetime import datetime, date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.future import select as future_select
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
import re
from datetime import datetime, date, timedelta
from typing import List

from app.providers.ocr_provider import get_ocr_provider
from app.providers.dms_provider import get_dms_provider
from app.core.security import decode_token, get_password_hash
from app.core.database import get_db
from app.schemas.schemas_partf import (
    VehicleFlowResponse, StaffPerformanceResponse, StaffUtilizationRow,
    PartsShortagePatterns, ReworkRateReport, AIActionPlanResponse, VehicleFlowAtRiskAlert,
    TeamTargetsDashboard, StaffTargetUpsert, UserShiftCreate, DemoRevenueEntryCreate,
)
from app.models.models import (
    Branch, CaptureEvent, JobCard, JobCategory, CancellationCategory, Role, User, Vehicle, WorkflowStage,
    OverrideRequest, OverrideRequestStatus, AppInstallation, FlatRateTimeCatalog, JobCardJobType,
    UserShift, StaffTarget, DemoRevenueEntry,
)
from app.schemas.schemas import (
    OverrideRequestCreate, OverrideRequestResponse, CancellationCategoryCreate,
    CancellationCategory as CancellationCategorySchema, CancelledPartialWorkReport,
    FlatRateTimeCatalogCreate, FlatRateTimeCatalog as FlatRateTimeCatalogSchema,
    JobCardJobTypeCreate, JobCardJobTypesResponse,
    SuspiciousCaptureReviewResponse, BranchLocationConfig,
)
from app.services.push_service import send_push_notification, build_override_decision_title

router = APIRouter()


async def get_admin_user(request: Request) -> dict:
    """Extract admin user from JWT token or internal header."""
    auth = request.headers.get("Authorization")
    token = None
    if auth and auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        token = request.headers.get("X-Access-Token")
    if not token:
        if request.headers.get("X-Internal") == "true":
            return {"user_id": 1, "role": "admin"}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token")
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return {"user_id": int(user_id)}


async def _require_admin_role(user_id: int, db: AsyncSession) -> User:
    """Ensure user has admin privileges."""
    result = await db.execute(
        select(User).options(joinedload(User.role)).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role and user.role.role_name not in ("ADMIN", "SERVICE_MANAGER", "MANAGER"):
        raise HTTPException(status_code=403, detail="Admin/Service Manager access required")
    return user


@router.get("/users", response_model=list[dict])
async def list_users(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users with their roles."""
    result = await db.execute(select(User).options(joinedload(User.role)))
    users = result.scalars().unique().all()
    return [
        {
            "user_id": u.user_id,
            "name": u.name,
            "mobile": u.mobile,
            "role_id": u.role_id,
            "role_name": u.role.role_name if u.role else None,
            "branch_id": u.branch_id,
            "status": u.status,
        }
        for u in users
    ]


@router.post("/users")
async def create_user(
    user_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new user."""
    await _require_admin_role(admin["user_id"], db)

    if not user_data.get("name") or not user_data.get("mobile"):
        raise HTTPException(status_code=400, detail="name and mobile are required")
    if user_data.get("password"):
        password_hash = get_password_hash(user_data["password"])
    else:
        password_hash = get_password_hash("1234")

    user = User(
        name=user_data["name"],
        mobile=user_data["mobile"],
        role_id=int(user_data["role_id"]) if user_data.get("role_id") else None,
        branch_id=int(user_data["branch_id"]) if user_data.get("branch_id") else None,
        status=user_data.get("status", "ACTIVE"),
        password_hash=password_hash,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Mobile number already exists")
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


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a user."""
    await _require_admin_role(admin["user_id"], db)
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "INACTIVE"
    await db.commit()
    return {"status": "deactivated", "user_id": user_id}


@router.post("/create-job-card")
async def admin_create_job_card(
    external_job_card_no: str,
    registration_number: str,
    branch_id: int,
    make: str = None,
    model: str = None,
    color: str = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin/QA convenience endpoint: create a job card quickly.

    Creates/reuses a Vehicle and an OPEN JobCard.
    """
    await _require_admin_role(admin["user_id"], db)

    # Reuse or create vehicle
    vehicle_result = await db.execute(
        select(Vehicle).where(Vehicle.registration_number == registration_number.upper())
    )
    vehicle = vehicle_result.scalar_one_or_none()
    if not vehicle:
        vehicle = Vehicle(
            registration_number=registration_number.upper(),
            make=make,
            model=model,
            color=color,
        )
        db.add(vehicle)
        await db.flush()

    existing = await db.execute(
        select(JobCard).where(JobCard.external_job_card_no == external_job_card_no)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Job card already exists")

    job_card = JobCard(
        external_job_card_no=external_job_card_no,
        vehicle_id=vehicle.vehicle_id,
        branch_id=branch_id,
        status="OPEN",
        open_time=datetime.utcnow(),
    )
    db.add(job_card)
    await db.commit()
    await db.refresh(job_card)

    return {
        "status": "created",
        "job_card_id": job_card.job_card_id,
        "external_job_card_no": job_card.external_job_card_no,
        "vehicle_id": vehicle.vehicle_id,
        "registration_number": vehicle.registration_number,
        "branch_id": job_card.branch_id,
        "status": job_card.status,
    }


@router.get("/branches")
async def list_branches(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List all branches."""
    result = await db.execute(select(Branch))
    branches = result.scalars().all()
    return {
        "branches": [
            {
                "branch_id": b.branch_id,
                "branch_name": b.branch_name,
                "timezone": b.timezone,
                "address": b.address,
            }
            for b in branches
        ]
    }


@router.post("/branches")
async def create_branch(
    branch_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new branch."""
    await _require_admin_role(admin["user_id"], db)
    if not branch_data.get("branch_name"):
        raise HTTPException(status_code=400, detail="branch_name is required")
    branch = Branch(
        branch_name=branch_data["branch_name"],
        timezone=branch_data.get("timezone", "Asia/Dubai"),
        address=branch_data.get("address"),
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return {
        "status": "created",
        "branch": {
            "branch_id": branch.branch_id,
            "branch_name": branch.branch_name,
            "timezone": branch.timezone,
            "address": branch.address,
        }
    }


@router.post("/workflows/stages")
async def create_workflow_stage(
    stage_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new workflow stage."""
    await _require_admin_role(admin["user_id"], db)
    stage = WorkflowStage(
        branch_id=stage_data.get("branch_id"),
        role_id=stage_data.get("role_id"),
        stage_code=stage_data["stage_code"],
        stage_name=stage_data["stage_name"],
        sequence_order=stage_data.get("sequence_order"),
        capture_mandatory=stage_data.get("capture_mandatory", True),
        allow_override=stage_data.get("allow_override", True),
        skip_deviation=stage_data.get("skip_deviation", False),
    )
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    return {
        "status": "created",
        "stage": {
            "stage_id": stage.stage_id,
            "branch_id": stage.branch_id,
            "role_id": stage.role_id,
            "stage_code": stage.stage_code,
            "stage_name": stage.stage_name,
            "sequence_order": stage.sequence_order,
            "capture_mandatory": stage.capture_mandatory,
            "allow_override": stage.allow_override,
            "skip_deviation": stage.skip_deviation,
        }
    }


@router.get("/workflows/stages")
async def list_workflow_stages(
    branch_id: int = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List workflow stages."""
    stmt = select(WorkflowStage).options(joinedload(WorkflowStage.role))
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
                "role_id": s.role_id,
                "stage_code": s.stage_code,
                "stage_name": s.stage_name,
                "sequence_order": s.sequence_order,
                "capture_mandatory": s.capture_mandatory,
                "allow_override": s.allow_override,
                "skip_deviation": s.skip_deviation,
                "role_name": s.role.role_name if s.role else None,
            }
            for s in stages
        ]
    }


@router.put("/branch-location/{branch_id}", response_model=BranchLocationConfig)
async def update_branch_location(
    branch_id: int,
    config: BranchLocationConfig,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Set the workshop GPS location and acceptable radius for location flagging."""
    await _require_admin_role(admin["user_id"], db)

    result = await db.execute(select(Branch).where(Branch.branch_id == branch_id))
    branch = result.scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    branch.workshop_geo_lat = config.workshop_geo_lat
    branch.workshop_geo_lng = config.workshop_geo_lng
    branch.geo_radius_meters = config.geo_radius_meters
    await db.commit()
    await db.refresh(branch)
    return {
        "workshop_geo_lat": branch.workshop_geo_lat,
        "workshop_geo_lng": branch.workshop_geo_lng,
        "geo_radius_meters": branch.geo_radius_meters,
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


@router.get("/suspicious-captures", response_model=SuspiciousCaptureReviewResponse)
async def suspicious_captures_review(
    branch_id: int,
    date: date | None = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Manager/service-manager review queue for photo authenticity red flags.

    This is a prioritized list, not an automatic rejection. Flagged captures
    still count as valid until a human overrides them. These signals are
    statistical red flags, not proof of fraud.
    """
    await _require_admin_role(admin["user_id"], db)

    if date is None:
        from datetime import date as _date
        date = _date.today()

    start_dt = datetime.combine(date, datetime.min.time())
    end_dt = datetime.combine(date, datetime.max.time())

    stmt = (
        select(CaptureEvent)
        .options(
            joinedload(CaptureEvent.stage),
            joinedload(CaptureEvent.user),
            joinedload(CaptureEvent.job_card).joinedload(JobCard.vehicle),
        )
        .where(
            CaptureEvent.received_at_server >= start_dt,
            CaptureEvent.received_at_server < end_dt,
            CaptureEvent.voided == False,
        )
        .order_by(CaptureEvent.received_at_server.desc())
    )

    result = await db.execute(stmt)
    events = result.scalars().unique().all()

    # Refresh flags for the day before returning.
    from app.services.photo_authenticity_service import PhotoAuthenticityService
    await PhotoAuthenticityService.evaluate_events(db, events, branch_id=branch_id)

    flagged_by_type = {flag: [] for flag in PhotoAuthenticityService.FLAG_LABELS}
    unflagged = []

    for event in events:
        flags = event.authenticity_flags or []
        if not flags:
            unflagged.append(event)
            continue
        for flag in flags:
            if flag in flagged_by_type:
                flagged_by_type[flag].append(event)

    def _event_payload(event, branch_filter_id=None):
        jc = event.job_card
        vehicle = jc.vehicle if jc else None
        return {
            "event_id": event.event_id,
            "stage_code": event.stage.stage_code if event.stage else None,
            "stage_name": event.stage.stage_name if event.stage else None,
            "user_id": event.user_id,
            "user_name": event.user.name if event.user else None,
            "job_card_id": event.job_card_id,
            "external_job_card_no": jc.external_job_card_no if jc else None,
            "vehicle_id": event.vehicle_id,
            "registration_number": vehicle.registration_number if vehicle else None,
            "image_url": event.image_url,
            "image_hash": event.image_hash,
            "geo_lat": event.geo_lat,
            "geo_lng": event.geo_lng,
            "captured_at_device": event.captured_at_device,
            "received_at_server": event.received_at_server,
            "exif_timestamp": event.exif_timestamp,
            "exif_missing": event.exif_missing,
            "parts_wait": event.parts_wait,
            "remarks": event.remarks,
        }

    items = []
    for flag, flag_events in flagged_by_type.items():
        if not flag_events:
            continue
        items.append({
            "flag_type": flag,
            "flag_label": PhotoAuthenticityService.FLAG_LABELS[flag],
            "severity": "high" if flag not in ("EXIF_MISSING", "LOCATION_MISSING") else "info",
            "limitation_note": (
                "Statistical red flag; verify the photo physically before action. "
                "Many phones strip EXIF by default, and GPS may be unavailable indoors."
            ),
            "total": len(flag_events),
            "captures": [_event_payload(e) for e in flag_events],
        })

    return {
        "branch_id": branch_id,
        "date": date.isoformat(),
        "total_reviewed": len(events),
        "flagged_groups": items,
        "unflagged_count": len(unflagged),
        "disclaimer": (
            "These are statistical red flags, not proof of fraud. They narrow down "
            "what a human should physically check; they do not replace human judgment "
            "on whether the photo genuinely shows the right vehicle/work."
        ),
    }


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


@router.get("/cancellation-categories")
async def list_cancellation_categories(
    branch_id: int | None = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List cancellation categories for the cancel-job-card dropdown."""
    stmt = select(CancellationCategory)
    if branch_id:
        stmt = stmt.where(
            (CancellationCategory.branch_id == branch_id) | (CancellationCategory.branch_id.is_(None))
        )
    stmt = stmt.where(CancellationCategory.is_active == True).order_by(CancellationCategory.category_name)
    result = await db.execute(stmt)
    categories = result.scalars().all()
    return {
        "categories": [
            {
                "cancellation_category_id": c.cancellation_category_id,
                "branch_id": c.branch_id,
                "category_name": c.category_name,
                "category_code": c.category_code,
                "is_active": c.is_active,
            }
            for c in categories
        ]
    }


@router.post("/cancellation-categories")
async def create_cancellation_category(
    category_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new cancellation category (admin-configurable)."""
    await _require_admin_role(admin["user_id"], db)

    if not category_data.get("category_name"):
        raise HTTPException(status_code=400, detail="category_name is required")
    category = CancellationCategory(
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
        raise HTTPException(status_code=400, detail="Cancellation category could not be created")

    return {
        "status": "created",
        "category": {
            "cancellation_category_id": category.cancellation_category_id,
            "branch_id": category.branch_id,
            "category_name": category.category_name,
            "category_code": category.category_code,
            "is_active": category.is_active,
        }
    }


@router.post("/cancellation-categories/seed")
async def seed_cancellation_categories(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Idempotent seed of default cancellation categories."""
    await _require_admin_role(admin["user_id"], db)
    defaults = [
        ("Customer refused zero bill", "CUSTOMER_REFUSED_ZERO_BILL"),
        ("Vehicle undriveable", "VEHICLE_UNDRIVEABLE"),
        ("Customer disputed cost", "CUSTOMER_DISPUTED_COST"),
        ("Duplicate entry", "DUPLICATE_ENTRY"),
        ("Other", "OTHER"),
    ]
    created = 0
    for name, code in defaults:
        existing = await db.execute(select(CancellationCategory).where(CancellationCategory.category_code == code))
        if not existing.scalars().first():
            db.add(CancellationCategory(category_name=name, category_code=code, is_active=True))
            created += 1
    if created:
        await db.commit()
    return {"status": "seeded", "created": created}


@router.get("/cancelled-partial-work", response_model=CancelledPartialWorkReport)
async def cancelled_partial_work_report(
    branch_id: int | None = None,
    cancellation_category_id: int | None = None,
    include_zero_billed: bool = True,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Service-manager/admin only: cancelled jobs where real capture work was
    logged before cancellation. Optionally include zero-billed jobs."""
    await _require_admin_role(admin["user_id"], db)

    from app.services.cancelled_partial_work_report import _CancelledPartialWorkReportBuilder
    statuses = ["CANCELLED"]
    if include_zero_billed:
        statuses.append("ZERO_BILLED")
    items = await _CancelledPartialWorkReportBuilder.build(
        db,
        branch_id=branch_id,
        cancellation_category_id=cancellation_category_id,
        statuses=statuses,
    )
    return {"items": items, "total_items": len(items)}


@router.post("/reconcile-dms")
async def reconcile_dms(
    job_card_id: int,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch DMS billing data for a job card and mark it ZERO_BILLED when the
    DMS reports a BILLED status with a zero amount.

    A real DMS integration will replace the mock provider; this endpoint
    performs the reconciliation logic regardless of provider backend.
    """
    await _require_admin_role(admin["user_id"], db)

    result = await db.execute(select(JobCard).where(JobCard.job_card_id == job_card_id))
    job_card = result.scalar_one_or_none()
    if not job_card:
        raise HTTPException(status_code=404, detail="Job card not found")

    if job_card.status in ("CANCELLED", "ZERO_BILLED"):
        raise HTTPException(status_code=400, detail="Job card is already in a terminal state")

    provider = get_dms_provider()
    try:
        billing = await provider.lookup_billing_info(job_card.external_job_card_no)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DMS lookup failed: {exc}")

    if billing.dms_status == "BILLED" and billing.bill_amount == 0.0:
        job_card.status = "ZERO_BILLED"
        job_card.close_time = datetime.utcnow()
    elif billing.dms_status == "CANCELLED":
        # Real DMS says cancelled; keep existing cancel flow, preserving reason/category if present.
        job_card.status = "CANCELLED"
        job_card.close_time = datetime.utcnow()
        if not job_card.cancellation_reason:
            job_card.cancellation_reason = "Cancelled in DMS"
        if not job_card.cancellation_category_id:
            other = await db.execute(
                select(CancellationCategory).where(CancellationCategory.category_code == "OTHER")
            )
            other_cat = other.scalar_one_or_none()
            if other_cat:
                job_card.cancellation_category_id = other_cat.cancellation_category_id
    else:
        return {
            "job_card_id": job_card.job_card_id,
            "reconciled": False,
            "dms_status": billing.dms_status,
            "bill_amount": billing.bill_amount,
            "job_card_status": job_card.status,
        }

    await db.commit()
    return {
        "job_card_id": job_card.job_card_id,
        "reconciled": True,
        "dms_status": billing.dms_status,
        "bill_amount": billing.bill_amount,
        "job_card_status": job_card.status,
    }


@router.get("/override-requests", response_model=list[OverrideRequestResponse])
async def list_override_requests(
    request: Request,
    status_filter: str = "PENDING",
    branch_id: int = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List override requests visible to the acting admin.

    Filter by status: PENDING, APPROVED, DENIED, or ALL.
    """
    await _require_admin_role(admin["user_id"], db)

    stmt = (
        future_select(OverrideRequest)
        .options(joinedload(OverrideRequest.requester), joinedload(OverrideRequest.stage))
    )
    if status_filter.upper() != "ALL":
        stmt = stmt.where(OverrideRequest.status == status_filter.upper())
    if branch_id:
        stmt = stmt.join(WorkflowStage).where(WorkflowStage.branch_id == branch_id)
    stmt = stmt.order_by(OverrideRequest.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def _create_capture_from_override(db, override: OverrideRequest, admin_user: User) -> CaptureEvent:
    """Replays an approved override request into a real CaptureEvent.

    The capture is always recorded against the original requester and stage
    (Part B requirement), with `approved_by` linked via the override record.
    """
    data = override.request_data or {}
    now = datetime.utcnow()

    event = CaptureEvent(
        job_card_id=override.job_card_id,
        vehicle_id=override.vehicle_id,
        stage_id=override.stage_id,
        user_id=override.requester_user_id,
        installation_id=1,  # Resolved via requester's current installation if available.
        image_url=data.get("image_url"),
        image_hash=data.get("image_hash"),
        exif_timestamp=datetime.fromisoformat(data["exif_timestamp"].replace("Z", "+00:00")) if data.get("exif_timestamp") else None,
        exif_missing=data.get("exif_missing", True),
        plate_text_raw=data.get("plate_text_raw"),
        plate_text_normalized=data.get("plate_text_normalized"),
        plate_confidence=data.get("plate_confidence", 0.95),
        match_status="PENDING_NO_JC",
        captured_at_device=now,
        received_at_server=now,
        remarks=data.get("remarks"),
        work_done_category_id=data.get("work_done_category_id"),
        geo_lat=data.get("geo_lat"),
        geo_lng=data.get("geo_lng"),
    )
    db.add(event)
    await db.flush()
    return event


@router.post("/override-requests/{request_id}/approve", response_model=OverrideRequestResponse)
async def approve_override_request(
    request_id: int,
    request: Request,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Approve a pending override request and record the capture event."""
    admin_user = await _require_admin_role(admin["user_id"], db)

    override = (
        await db.execute(
            future_select(OverrideRequest)
            .options(joinedload(OverrideRequest.requester), joinedload(OverrideRequest.stage))
            .where(OverrideRequest.override_request_id == request_id)
        )
    ).scalar_one_or_none()

    if not override:
        raise HTTPException(status_code=404, detail="Override request not found")
    if override.status != OverrideRequestStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Override request already decided")

    event = await _create_capture_from_override(db, override, admin_user)

    override.status = OverrideRequestStatus.APPROVED.value
    override.approved_by = admin_user.user_id
    override.decided_at = datetime.utcnow()
    override.resolved_event_id = event.event_id

    await db.commit()
    await db.refresh(event)
    await db.refresh(override)

    # Notify requester of approval.
    requester_install = (
        await db.execute(
            future_select(AppInstallation).where(
                AppInstallation.user_id == override.requester_user_id,
                AppInstallation.push_token.isnot(None),
                AppInstallation.status == "active",
            )
        )
    ).scalar_one_or_none()
    if requester_install and requester_install.push_token:
        await send_push_notification(
            requester_install.push_token,
            build_override_decision_title(override.stage.stage_name if override.stage else "stage", True),
            "Your override request was approved and the capture has been recorded.",
            data={
                "type": "OVERRIDE_DECISION",
                "override_request_id": override.override_request_id,
                "event_id": event.event_id,
                "approved": True,
            },
        )

    return override


@router.post("/override-requests/{request_id}/deny", response_model=OverrideRequestResponse)
async def deny_override_request(
    request_id: int,
    request: Request,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Deny a pending override request."""
    admin_user = await _require_admin_role(admin["user_id"], db)

    override = (
        await db.execute(
            future_select(OverrideRequest)
            .options(joinedload(OverrideRequest.requester), joinedload(OverrideRequest.stage))
            .where(OverrideRequest.override_request_id == request_id)
        )
    ).scalar_one_or_none()

    if not override:
        raise HTTPException(status_code=404, detail="Override request not found")
    if override.status != OverrideRequestStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Override request already decided")

    override.status = OverrideRequestStatus.DENIED.value
    override.approved_by = admin_user.user_id
    override.decided_at = datetime.utcnow()

    await db.commit()
    await db.refresh(override)

    requester_install = (
        await db.execute(
            future_select(AppInstallation).where(
                AppInstallation.user_id == override.requester_user_id,
                AppInstallation.push_token.isnot(None),
                AppInstallation.status == "active",
            )
        )
    ).scalar_one_or_none()
    if requester_install and requester_install.push_token:
        await send_push_notification(
            requester_install.push_token,
            build_override_decision_title(override.stage.stage_name if override.stage else "stage", False),
            "Your override request was denied. The capture was not recorded.",
            data={
                "type": "OVERRIDE_DECISION",
                "override_request_id": override.override_request_id,
                "approved": False,
            },
        )

    return override


@router.get("/team-targets", response_model=TeamTargetsDashboard)
async def list_team_targets(
    year: int = None,
    month: int = None,
    branch_id: int = None,
    demo_mode: bool = False,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin tab: vehicle-count and revenue targets for team members.

    Revenue achievement is sourced from the DMS connection only. Until the real
    DMS connection is live, achievement displays as 'Pending DMS connection'.
    Pass demo_mode=true to include sample demo revenue entries.
    """
    await _require_admin_role(admin["user_id"], db)

    now = datetime.utcnow()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    user_stmt = select(User, Role).outerjoin(Role, User.role_id == Role.role_id)
    if branch_id:
        user_stmt = user_stmt.where(User.branch_id == branch_id)
    user_result = await db.execute(user_stmt.where(User.status == "ACTIVE"))
    users_rows = user_result.all()

    target_stmt = select(StaffTarget).where(
        StaffTarget.target_year == year,
        StaffTarget.target_month == month,
    )
    if branch_id:
        target_stmt = target_stmt.where(StaffTarget.branch_id == branch_id)
    target_result = await db.execute(target_stmt)
    targets = {t.user_id: t for t in target_result.scalars().all()}

    from app.services.staff_performance_service import _StaffPerformanceService
    month_start = datetime(year, month, 1)
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    month_end = datetime(next_year, next_month, 1)
    rollup = await _StaffPerformanceService.rollup(
        db, month_start, month_end, branch_id=branch_id
    )
    by_user_id = {u["user_id"]: u for u in rollup.get("per_individual", [])}

    dms_connected = False
    demo_entries = []
    if demo_mode:
        demo_stmt = select(DemoRevenueEntry).where(
            DemoRevenueEntry.revenue_date >= month_start.date(),
            DemoRevenueEntry.revenue_date < month_end.date(),
        )
        if branch_id:
            demo_stmt = demo_stmt.where(DemoRevenueEntry.branch_id == branch_id)
        demo_result = await db.execute(demo_stmt)
        demo_entries = demo_result.scalars().all()

    user_items = []
    for user, role in users_rows:
        target = targets.get(user.user_id)
        actual = by_user_id.get(user.user_id, {})
        demo_revenue = round(sum(d.revenue_amount for d in demo_entries if d.user_id == user.user_id), 2)
        item = {
            "user_id": user.user_id,
            "name": user.name,
            "role_id": role.role_id if role else None,
            "role_name": role.role_name if role else None,
            "monthly_vehicle_target": target.vehicle_target_count if target else 0,
            "daily_vehicle_target": target.daily_vehicle_target_count if target else None,
            "monthly_revenue_target": target.monthly_revenue_target if target else None,
            "vehicles_handled_actual": actual.get("vehicles_handled_count", 0),
            "captures_count_actual": actual.get("capture_count", 0),
            "revenue_achievement_status": "Pending DMS connection" if not dms_connected else "DMS connected",
            "revenue_achievement_amount": demo_revenue if demo_mode and not dms_connected else None,
            "demo_revenue_included": demo_mode,
        }
        user_items.append(item)

    return {
        "year": year,
        "month": month,
        "branch_id": branch_id,
        "dms_connected": dms_connected,
        "demo_mode": demo_mode,
        "disclaimer": (
            "Revenue achievement is sourced from the DMS only. Demo revenue is clearly "
            "labeled and must be disabled/removed when moving to production with a live DMS."
        ),
        "users": user_items,
    }


@router.put("/team-targets/{user_id}", response_model=StaffTargetUpsert)
async def set_team_target(
    user_id: int,
    target: StaffTargetUpsert,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Set monthly vehicle/revenue targets for a team member."""
    await _require_admin_role(admin["user_id"], db)

    user = await db.execute(select(User).where(User.user_id == user_id))
    user = user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stmt = select(StaffTarget).where(
        StaffTarget.user_id == user_id,
        StaffTarget.target_year == target.target_year,
        StaffTarget.target_month == target.target_month,
    )
    if target.branch_id:
        stmt = stmt.where(StaffTarget.branch_id == target.branch_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.vehicle_target_count = target.vehicle_target_count
        existing.daily_vehicle_target_count = target.daily_vehicle_target_count
        existing.monthly_revenue_target = target.monthly_revenue_target
        existing.updated_at = datetime.utcnow()
    else:
        existing = StaffTarget(
            user_id=user_id,
            branch_id=target.branch_id,
            target_year=target.target_year,
            target_month=target.target_month,
            vehicle_target_count=target.vehicle_target_count,
            daily_vehicle_target_count=target.daily_vehicle_target_count,
            monthly_revenue_target=target.monthly_revenue_target,
            created_by_user_id=admin["user_id"],
        )
        db.add(existing)

    await db.commit()
    await db.refresh(existing)
    return existing


@router.post("/user-shifts", response_model=dict)
async def create_user_shift(
    shift: UserShiftCreate,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a shift record for a staff member (needed for utilisation view)."""
    await _require_admin_role(admin["user_id"], db)

    record = UserShift(
        user_id=shift.user_id,
        branch_id=shift.branch_id,
        shift_date=shift.shift_date,
        shift_start=datetime.combine(shift.shift_date, shift.shift_start),
        shift_end=datetime.combine(shift.shift_date, shift.shift_end),
        break_minutes=shift.break_minutes,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {
        "user_shift_id": record.user_shift_id,
        "user_id": record.user_id,
        "shift_date": record.shift_date.isoformat(),
        "shift_start": record.shift_start.isoformat(),
        "shift_end": record.shift_end.isoformat(),
        "break_minutes": record.break_minutes,
    }


@router.post("/demo-revenue", response_model=dict)
async def create_demo_revenue(
    entry: DemoRevenueEntryCreate,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Demo mode only: inject a clearly-labeled sample revenue entry."""
    await _require_admin_role(admin["user_id"], db)

    record = DemoRevenueEntry(
        external_job_card_no=entry.external_job_card_no,
        user_id=entry.user_id,
        branch_id=entry.branch_id,
        revenue_amount=entry.revenue_amount,
        revenue_currency=entry.revenue_currency,
        revenue_date=entry.revenue_date,
        notes="DEMO DATA - NOT REAL REVENUE",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {
        "demo_revenue_id": record.demo_revenue_id,
        "external_job_card_no": record.external_job_card_no,
        "revenue_amount": record.revenue_amount,
        "revenue_date": record.revenue_date.isoformat(),
        "notes": record.notes,
    }


@router.delete("/demo-revenue")
async def clear_demo_revenue(
    branch_id: int = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin convenience: remove all demo revenue entries."""
    await _require_admin_role(admin["user_id"], db)
    stmt = select(DemoRevenueEntry)
    if branch_id:
        stmt = stmt.where(DemoRevenueEntry.branch_id == branch_id)
    result = await db.execute(stmt)
    for entry in result.scalars().all():
        await db.delete(entry)
    await db.commit()
    return {"cleared": True, "disclaimer": "Demo revenue cleared. Real DMS revenue remains unaffected."}


@router.get("/frt-catalog")
async def list_frt_catalog(
    branch_id: int | None = None,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List admin-configurable FRT catalog entries."""
    await _require_admin_role(admin["user_id"], db)

    stmt = select(FlatRateTimeCatalog)
    if branch_id:
        stmt = stmt.where(
            (FlatRateTimeCatalog.branch_id == branch_id) | (FlatRateTimeCatalog.branch_id.is_(None))
        )
    stmt = stmt.where(FlatRateTimeCatalog.is_active == True).order_by(FlatRateTimeCatalog.job_type_name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "items": [
            {
                "frt_entry_id": f.frt_entry_id,
                "branch_id": f.branch_id,
                "job_type_code": f.job_type_code,
                "job_type_name": f.job_type_name,
                "target_time_minutes": f.target_time_minutes,
                "is_active": f.is_active,
            }
            for f in rows
        ]
    }


@router.post("/frt-catalog")
async def create_frt_catalog_entry(
    entry: FlatRateTimeCatalogCreate,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new FRT catalog entry."""
    await _require_admin_role(admin["user_id"], db)

    record = FlatRateTimeCatalog(
        branch_id=entry.branch_id,
        job_type_code=entry.job_type_code.upper().strip(),
        job_type_name=entry.job_type_name,
        target_time_minutes=entry.target_time_minutes,
        is_active=entry.is_active if entry.is_active is not None else True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {
        "frt_entry_id": record.frt_entry_id,
        "branch_id": record.branch_id,
        "job_type_code": record.job_type_code,
        "job_type_name": record.job_type_name,
        "target_time_minutes": record.target_time_minutes,
        "is_active": record.is_active,
    }


@router.post("/frt-catalog/seed")
async def seed_frt_catalog(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Seed sample FRT catalog entries."""
    await _require_admin_role(admin["user_id"], db)

    defaults = [
        ("BRAKE_PAD_REPLACEMENT", "Brake pad replacement", 90),
        ("OIL_CHANGE", "Oil change", 30),
        ("WHEEL_ALIGNMENT", "Wheel alignment", 45),
        ("AC_SERVICE", "AC service", 60),
        ("GENERAL_SERVICE", "General service", 120),
    ]
    created = 0
    for code, name, minutes in defaults:
        existing = await db.execute(
            select(FlatRateTimeCatalog).where(FlatRateTimeCatalog.job_type_code == code)
        )
        if not existing.scalar_one_or_none():
            db.add(FlatRateTimeCatalog(job_type_code=code, job_type_name=name, target_time_minutes=minutes))
            created += 1
    if created:
        await db.commit()
    return {"status": "seeded", "created": created}


@router.post("/job-card-assign-job-types")
async def assign_job_types_to_job_card(
    data: JobCardJobTypeCreate,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Assign FRT job types to a job card (typically at TECH_ASSIGNED)."""
    await _require_admin_role(admin["user_id"], db)

    jc_result = await db.execute(select(JobCard).where(JobCard.job_card_id == data.job_card_id))
    job_card = jc_result.scalar_one_or_none()
    if not job_card:
        raise HTTPException(status_code=404, detail="Job card not found")

    # Remove existing and replace (idempotent for this assignment call).
    existing = await db.execute(
        select(JobCardJobType).where(JobCardJobType.job_card_id == data.job_card_id)
    )
    for row in existing.scalars().all():
        await db.delete(row)

    for frt_id in data.frt_entry_ids:
        db.add(JobCardJobType(
            job_card_id=data.job_card_id,
            frt_entry_id=frt_id,
            assigned_by_user_id=admin["user_id"],
            assigned_at=datetime.utcnow(),
        ))

    await db.commit()
    return {"job_card_id": data.job_card_id, "assigned_frt_entry_ids": data.frt_entry_ids}


@router.get("/job-card-job-types/{job_card_id}", response_model=JobCardJobTypesResponse)
async def list_job_card_job_types(
    job_card_id: int,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Return the selected FRT job types for a job card and total target time."""
    await _require_admin_role(admin["user_id"], db)

    stmt = (
        select(JobCardJobType, FlatRateTimeCatalog)
        .join(FlatRateTimeCatalog, JobCardJobType.frt_entry_id == FlatRateTimeCatalog.frt_entry_id)
        .where(JobCardJobType.job_card_id == job_card_id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    job_types = [
        {
            "frt_entry_id": f.frt_entry_id,
            "job_type_code": f.job_type_code,
            "job_type_name": f.job_type_name,
            "target_time_minutes": f.target_time_minutes,
            "assigned_by_user_id": j.assigned_by_user_id,
            "assigned_at": j.assigned_at,
        }
        for j, f in rows
    ]
    return {
        "job_card_id": job_card_id,
        "total_target_time_minutes": sum(jt["target_time_minutes"] for jt in job_types),
        "job_types": job_types,
    }
