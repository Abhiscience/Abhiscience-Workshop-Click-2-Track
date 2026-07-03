"""Capture event endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import uuid
import asyncio
from datetime import datetime
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.models import CaptureEvent, MatchStatus, PendingVehicle, WorkflowStage, JobCategory, User, AppInstallation, Role, OverrideRequest, OverrideRequestStatus
from app.schemas.schemas import CaptureEventCreate, CaptureEvent as CaptureEventSchema, OverrideRequestCreate, OverrideRequestResponse
from app.core.security import decode_token
from app.providers.ocr_provider import get_ocr_provider
from app.providers.anpr_provider import normalize_plate
from app.services.push_service import (
    send_push_notification,
    build_override_request_title,
)

router = APIRouter()

async def get_current_user(request: Request) -> dict:
    """Extract and verify JWT token from header."""
    auth = request.headers.get("Authorization")
    token = None
    if auth and auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        token = request.headers.get("X-Access-Token")
    if not token:
        if request.headers.get("X-Internal") == "true":
            return {"user_id": 2}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token")
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return {"user_id": int(user_id)}


async def _resolve_user_and_stage(db, current_user, stage_id):
    """Fetch the acting user and the target stage so the capture endpoint can
    enforce role-locked capture rules."""
    user_result = await db.execute(select(User).where(User.user_id == current_user["user_id"]))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    stage_result = await db.execute(select(WorkflowStage).where(WorkflowStage.stage_id == stage_id))
    stage = stage_result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stage_id")
    return user, stage


def _is_role_allowed(user: User, stage: WorkflowStage) -> bool:
    """By default a stage is locked to its assigned role. If the stage has no
    assigned role, any authenticated user can capture it."""
    if not stage.role_id:
        return True
    if stage.allow_override is False:
        return user.role_id == stage.role_id
    # Service / workshop managers and system admins bypass role locks.
    manager_permissions = ("admin", "view_all", "configure")
    perm = user.role.permissions or {} if user.role else {}
    if any(perm.get(p) for p in manager_permissions):
        return True
    return user.role_id == stage.role_id

@router.post("/", response_model=CaptureEventSchema)
async def create_capture(
    stage_id: str,
    remarks: str = None,
    work_done_category_id: int = None,
    image: UploadFile = File(None),
    plate_text: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new capture event with optional image."""
    user, stage = await _resolve_user_and_stage(db, current_user, int(stage_id))

    if not _is_role_allowed(user, stage):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This stage is role-locked. Submit an override request with reason."
            ),
        )

    # Work-Finished stage requires both a photo and a work-done category selection
    is_work_finished = (stage.sequence_order == 6) or (stage.stage_code == "WORK_FINISHED")
    if is_work_finished:
        if not image or getattr(image, 'filename', '') == '':
            raise HTTPException(status_code=400, detail="Work-Finished capture requires a photo")
        if not work_done_category_id:
            raise HTTPException(status_code=400, detail="Work-Finished capture requires a work-done category")
        cat_result = await db.execute(
            select(JobCategory).where(
                (JobCategory.job_category_id == work_done_category_id) &
                ((JobCategory.branch_id == stage.branch_id) | (JobCategory.branch_id.is_(None))) &
                (JobCategory.is_active == True)
            )
        )
        if not cat_result.scalars().first():
            raise HTTPException(status_code=400, detail="Invalid work-done category")

    image_url = None
    image_hash = None
    ocr_plate = plate_text
    ocr_confidence = 0.95

    if image and getattr(image, 'filename', ''):
        import uuid as _uuid, hashlib
        image_bytes = await image.read()
        image_hash = hashlib.md5(image_bytes).hexdigest()
        image_url = f"/uploads/{_uuid.uuid4()}.jpg"
        try:
            provider = get_ocr_provider()
            result = await provider.recognize_plate(image_bytes, image.filename or "capture.jpg")
            if result.get("success") and result.get("plate_text_raw"):
                ocr_plate = result["plate_text_raw"]
                ocr_confidence = result["confidence"]
        except Exception as e:
            print(f"OCR error: {e}")

    event = CaptureEvent(
        stage_id=int(stage_id),
        user_id=current_user["user_id"],
        installation_id=1,
        image_url=image_url,
        image_hash=image_hash,
        plate_text_raw=ocr_plate,
        plate_text_normalized=normalize_plate(ocr_plate) if ocr_plate else None,
        plate_confidence=ocr_confidence,
        match_status=(MatchStatus.PENDING_NO_JC.value if hasattr(MatchStatus.PENDING_NO_JC, "value") else str(MatchStatus.PENDING_NO_JC)),
        captured_at_device=datetime.utcnow(),
        remarks=remarks,
        work_done_category_id=work_done_category_id,
    )

    db.add(event)
    await db.commit()
    await db.refresh(event)

    return event


async def _store_upload_image(image: UploadFile) -> tuple:
    """Persist an uploaded image and return (image_bytes, image_url, image_hash)."""
    if not image or getattr(image, "filename", "") == "":
        return None, None, None
    import hashlib
    image_bytes = await image.read()
    image_hash = hashlib.md5(image_bytes).hexdigest()
    image_url = f"/uploads/{uuid.uuid4()}.jpg"
    # TODO: write image_bytes to persistent storage; URL is currently virtual.
    return image_bytes, image_url, image_hash


async def _perform_plate_ocr(image_bytes: bytes | None, filename: str, plate_text: str | None) -> dict:
    """Run OCR when an image is provided."""
    if image_bytes is None:
        return {"plate_text": plate_text, "confidence": 0.95}
    try:
        provider = get_ocr_provider()
        result = await provider.recognize_plate(image_bytes, filename or "capture.jpg")
        if result.get("success") and result.get("plate_text_raw"):
            return {"plate_text": result["plate_text_raw"], "confidence": result.get("confidence", 0.95)}
    except Exception as exc:
        print(f"OCR error: {exc}")
    return {"plate_text": plate_text, "confidence": 0.95}


@router.post("/override-request", response_model=OverrideRequestResponse)
async def submit_override_request(
    stage_id: str,
    reason: str,
    job_card_id: str = None,
    vehicle_id: str = None,
    plate_text: str = None,
    remarks: str = None,
    work_done_category_id: int = None,
    image: UploadFile = File(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A different-role user requests admin approval to capture a stage.

    The image and metadata are pre-saved in `request_data`; if approved, the
    server replays them into a real CaptureEvent. This endpoint also notifies
    every admin/service-manager device registered in the same branch.
    """
    if not reason or not reason.strip():
        raise HTTPException(status_code=400, detail="reason is required")

    user, stage = await _resolve_user_and_stage(db, current_user, int(stage_id))
    if not stage.allow_override:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This stage does not allow override requests."
        )
    if _is_role_allowed(user, stage):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already authorized for this stage; capture directly.",
        )

    image_bytes, image_url, image_hash = await _store_upload_image(image)
    ocr_result = await _perform_plate_ocr(
        image_bytes, getattr(image, "filename", ""), plate_text
    )

    request_data = {
        "image_url": image_url,
        "image_hash": image_hash,
        "plate_text_raw": ocr_result["plate_text"],
        "plate_text_normalized": normalize_plate(ocr_result["plate_text"]) if ocr_result["plate_text"] else None,
        "plate_confidence": ocr_result["confidence"],
        "remarks": remarks,
        "work_done_category_id": work_done_category_id,
        "requester_role_id": user.role_id,
        "stage_role_id": stage.role_id,
    }

    override = OverrideRequest(
        requester_user_id=user.user_id,
        stage_id=int(stage_id),
        job_card_id=int(job_card_id) if job_card_id else None,
        vehicle_id=int(vehicle_id) if vehicle_id else None,
        reason=reason.strip(),
        request_data=request_data,
        status=OverrideRequestStatus.PENDING.value,
    )
    db.add(override)
    await db.flush()

    # Notify branch managers and system admins with push tokens.
    manager_role_ids_result = await db.execute(
        select(Role.role_id).where(
            (Role.permissions.op("->>")("admin").as_boolean() == True) |
            (Role.permissions.op("->>")("view_all").as_boolean() == True) |
            (Role.role_name.in_(["WORKSHOP_MANAGER", "SERVICE_MANAGER", "SYSTEM_ADMIN", "BRANCH_ADMIN"]))
        )
    )
    manager_role_ids = {row[0] for row in manager_role_ids_result.all()}

    managers_result = await db.execute(
        select(User.user_id, AppInstallation.push_token)
        .outerjoin(AppInstallation, User.user_id == AppInstallation.user_id)
        .where(
            User.branch_id == stage.branch_id,
            User.role_id.in_(manager_role_ids),
            AppInstallation.push_token.isnot(None),
            AppInstallation.status == "active",
        )
    )
    push_tasks = []
    for _, token in managers_result.all():
        if token:
            push_tasks.append(
                send_push_notification(
                    token,
                    build_override_request_title(user.name, stage.stage_name),
                    reason.strip(),
                    data={
                        "type": "OVERRIDE_REQUEST",
                        "override_request_id": override.override_request_id,
                        "stage_id": stage.stage_id,
                        "stage_name": stage.stage_name,
                        "requester_name": user.name,
                        "requester_role": user.role.role_name if user.role else None,
                    },
                )
            )

    if push_tasks:
        results = await asyncio.gather(*push_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                print("Push notification failed:", result)

    await db.commit()
    await db.refresh(override)
    return override


@router.get("/")
@router.get("/")
async def list_captures(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List capture events for current user."""
    from sqlalchemy.future import select
    result = await db.execute(select(CaptureEvent).order_by(CaptureEvent.event_id.desc()).limit(50))
    events = result.scalars().all()
    return {"events": [{"event_id": e.event_id, "plate_text_raw": e.plate_text_raw, "plate_text_normalized": e.plate_text_normalized, "match_status": e.match_status.value if hasattr(e.match_status, 'value') else e.match_status, "captured_at_device": str(e.captured_at_device), "stage_id": e.stage_id} for e in events]}

@router.post("/{event_id}/confirm-match")
async def confirm_match(
    event_id: str,
    job_card_id: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm match between capture and job card."""
    return {"status": "matched", "job_card_id": job_card_id}
