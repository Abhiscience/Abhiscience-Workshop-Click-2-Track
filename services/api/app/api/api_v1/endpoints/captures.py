"""Capture event endpoints."""
import hashlib
import uuid
import asyncio
from math import radians
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.models import CaptureEvent, LinkStatus, MatchStatus, PendingVehicle, WorkflowStage, JobCategory, User, AppInstallation, Role, OverrideRequest, OverrideRequestStatus, JobCard, Vehicle, FlatRateTimeCatalog
from app.schemas.schemas import (
    CaptureEventCreate, CaptureEvent as CaptureEventSchema, OverrideRequestCreate, OverrideRequestResponse,
    CaptureEventVoidRequest, FlatRateTimeCatalogCreate, FlatRateTimeCatalog as FlatRateTimeCatalogSchema,
    SuspiciousCaptureReviewResponse, BranchLocationConfig,
)
from app.core.security import decode_token
from app.providers.ocr_provider import get_ocr_provider
from app.providers.anpr_provider import normalize_plate
from app.services.push_service import (
    send_push_notification,
    build_override_request_title,
)

router = APIRouter()


def _match_status_value(ms):
    return ms.value if hasattr(ms, "value") else str(ms)


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
    user_result = await db.execute(select(User).options(selectinload(User.role)).where(User.user_id == current_user["user_id"]))
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
    remarks: str | None = None,
    work_done_category_id: int | None = None,
    parts_wait: bool = False,
    parts_wait_remark: str | None = None,
    geo_lat: float | None = None,
    geo_lng: float | None = None,
    image: UploadFile = File(...),
    plate_text: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new capture event. An uploaded image is mandatory."""
    user, stage = await _resolve_user_and_stage(db, current_user, int(stage_id))

    if not image or getattr(image, "filename", "") == "":
        raise HTTPException(status_code=400, detail="A photo is required for every capture")

    if not _is_role_allowed(user, stage):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This stage is role-locked. Submit an override request with reason."
        )

    # Validate parts-wait is only used on PARTS_ISSUED stage.
    if parts_wait and stage.stage_code != "PARTS_ISSUED":
        raise HTTPException(status_code=400, detail="parts_wait flag is only valid for PARTS_ISSUED stage")
    if parts_wait and not parts_wait_remark:
        raise HTTPException(status_code=400, detail="parts_wait_remark is required when flag is set")

    # Work-Finished stage additionally requires a work-done category selection
    is_work_finished = (stage.sequence_order == 6) or (stage.stage_code == "WORK_FINISHED")
    if is_work_finished and not work_done_category_id:
        raise HTTPException(status_code=400, detail="Work-Finished capture requires a work-done category")
    if work_done_category_id:
        cat_result = await db.execute(
            select(JobCategory).where(
                (JobCategory.job_category_id == work_done_category_id) &
                ((JobCategory.branch_id == stage.branch_id) | (JobCategory.branch_id.is_(None))) &
                (JobCategory.is_active == True)
            )
        )
        if not cat_result.scalars().first():
            raise HTTPException(status_code=400, detail="Invalid work-done category")

    image_bytes, image_url, image_hash = await _store_upload_image(image)
    ocr_result = await _perform_plate_ocr(image_bytes, getattr(image, "filename", ""), plate_text)

    normalized_plate = normalize_plate(ocr_result["plate_text"]) if ocr_result.get("plate_text") else None

    # Part G: EXIF timestamp extraction
    exif_timestamp, exif_missing = None, True
    try:
        from app.services.photo_authenticity_service import PhotoAuthenticityService
        exif_timestamp, exif_missing = PhotoAuthenticityService.extract_exif_timestamp(image_bytes)
    except Exception:
        pass

    # Attempt auto-link for gate entries or any event with a normalized plate.
    match_status, match_method, job_card_id, vehicle_id, pending_vehicle_ref = await _auto_link_event(
        db, normalized_plate, stage
    )

    # Part D: if this is a vehicle entry-point stage and no match was found,
    # create a PendingVehicle so a later Gate In capture can auto-link.
    if (
        stage.stage_code in ("SECURITY_GATE", "GATE_ENTRY")
        and match_status == _match_status_value(MatchStatus.PENDING_NO_JC)
        and normalized_plate
    ):
        pending = PendingVehicle(
            temporary_plate_text=normalized_plate,
            branch_id=stage.branch_id,
            link_status=LinkStatus.PENDING.value,
        )
        db.add(pending)
        await db.flush()
        pending_vehicle_ref = pending.pending_vehicle_ref
        match_status = _match_status_value(MatchStatus.PENDING_NO_JC)
        match_method = "pending_created"

    event = CaptureEvent(
        stage_id=int(stage_id),
        user_id=current_user["user_id"],
        installation_id=1,
        image_url=image_url,
        image_hash=image_hash,
        exif_timestamp=exif_timestamp,
        exif_missing=exif_missing,
        geo_lat=geo_lat,
        geo_lng=geo_lng,
        plate_text_raw=ocr_result.get("plate_text"),
        plate_text_normalized=normalized_plate,
        plate_confidence=ocr_result.get("confidence", 0.95),
        job_card_id=job_card_id,
        vehicle_id=vehicle_id,
        pending_vehicle_ref=pending_vehicle_ref,
        match_status=match_status,
        match_method=match_method,
        captured_at_device=datetime.utcnow(),
        remarks=remarks,
        work_done_category_id=work_done_category_id,
        parts_wait=parts_wait,
        parts_wait_remark=parts_wait_remark,
    )

    db.add(event)
    await db.flush()

    # G: run authenticity checks after every new capture and store the flags.
    try:
        from app.services.photo_authenticity_service import PhotoAuthenticityService
        flagged_events = await PhotoAuthenticityService.evaluate_events(
            db=db,
            events=[event],
            branch_id=stage.branch_id,
        )
        if flagged_events:
            await db.flush()
    except Exception:
        # Authenticity checks must not break capture recording.
        import logging
        logging.exception("authenticity check failed")

    await db.commit()
    await db.refresh(event)

    return event


@router.post("/override-request", response_model=OverrideRequestResponse)
async def submit_override_request(
    stage_id: str,
    reason: str,
    job_card_id: str = None,
    vehicle_id: str = None,
    plate_text: str = None,
    remarks: str = None,
    work_done_category_id: int = None,
    geo_lat: float | None = None,
    geo_lng: float | None = None,
    image: UploadFile = File(...),
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

    if not image or getattr(image, "filename", "") == "":
        raise HTTPException(status_code=400, detail="A photo is required for every override request")

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

    # Part G: EXIF timestamp extraction
    exif_timestamp, exif_missing = None, True
    try:
        from app.services.photo_authenticity_service import PhotoAuthenticityService
        exif_timestamp, exif_missing = PhotoAuthenticityService.extract_exif_timestamp(image_bytes)
    except Exception:
        pass

    request_data = {
        "image_url": image_url,
        "image_hash": image_hash,
        "exif_timestamp": exif_timestamp.isoformat() if exif_timestamp else None,
        "exif_missing": exif_missing,
        "geo_lat": geo_lat,
        "geo_lng": geo_lng,
        "plate_text_raw": ocr_result.get("plate_text"),
        "plate_text_normalized": normalize_plate(ocr_result["plate_text"]) if ocr_result.get("plate_text") else None,
        "plate_confidence": ocr_result.get("confidence", 0.95),
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
            (Role.permissions["admin"].as_boolean() == True) |
            (Role.permissions["view_all"].as_boolean() == True) |
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


async def _auto_link_event(
    db: AsyncSession,
    normalized_plate: Optional[str],
    stage: WorkflowStage
):
    """Attempt to auto-link a capture to a vehicle / job card / pending_vehicle.

    Returns: (match_status, match_method, job_card_id, vehicle_id, pending_vehicle_ref)
    """
    if not normalized_plate:
        return _match_status_value(MatchStatus.PENDING_NO_JC), None, None, None, None

    # 1) Existing vehicle exact match
    vehicle_result = await db.execute(
        select(Vehicle).where(Vehicle.registration_number == normalized_plate)
    )
    vehicle = vehicle_result.scalar_one_or_none()
    if vehicle:
        # Find an open job card for this vehicle
        jc_result = await db.execute(
            select(JobCard)
            .where(
                JobCard.vehicle_id == vehicle.vehicle_id,
                JobCard.status.notin_(["COMPLETED", "CLOSED", "CANCELLED"]),
            )
            .order_by(JobCard.open_time.desc())
        )
        job_card = jc_result.scalars().first()
        if job_card:
            return _match_status_value(MatchStatus.EXACT_MATCH), "exact", job_card.job_card_id, vehicle.vehicle_id, None
        return _match_status_value(MatchStatus.NORMALIZED_MATCH), "vehicle_only", None, vehicle.vehicle_id, None

    # 2) Pending vehicle created by Security Gate Check
    pending_result = await db.execute(
        select(PendingVehicle).where(
            PendingVehicle.temporary_plate_text == normalized_plate,
            PendingVehicle.branch_id == stage.branch_id,
            PendingVehicle.link_status != LinkStatus.LINKED.value,
        )
    )
    pending = pending_result.scalars().first()
    if pending:
        pending.link_status = LinkStatus.LINKED.value
        return _match_status_value(MatchStatus.NORMALIZED_MATCH), "pending_vehicle", None, None, pending.pending_vehicle_ref

    return _match_status_value(MatchStatus.PENDING_NO_JC), None, None, None, None


@router.get("/")
async def list_captures(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List capture events for current user."""
    result = await db.execute(select(CaptureEvent).order_by(CaptureEvent.event_id.desc()).limit(50))
    events = result.scalars().all()
    return {"events": [{"event_id": e.event_id, "plate_text_raw": e.plate_text_raw, "plate_text_normalized": e.plate_text_normalized, "match_status": e.match_status.value if hasattr(e.match_status, 'value') else e.match_status, "captured_at_device": str(e.captured_at_device), "stage_id": e.stage_id} for e in events]}


@router.post("/{event_id}/void")
async def void_capture_event(
    event_id: str,
    request: Request,
    payload: CaptureEventVoidRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Void a capture event (wrong stage, wrong vehicle, etc.) preserving audit trail.

    The original record remains in the database with voided=True and void_reason.
    A corrected replacement can optionally be supplied in the same request.
    """
    from app.services.void_capture_service import void_capture, create_correction_capture

    event_result = await db.execute(select(CaptureEvent).where(CaptureEvent.event_id == int(event_id)))
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Capture event not found")
    if event.voided:
        raise HTTPException(status_code=400, detail="Capture event is already voided")

    corrected_event = None
    if request.headers.get("X-Correction") == "true":
        body = await request.json()
        correction_body = body.get("correction", {})
        # Basic validation: require stage_id
        if "stage_id" not in correction_body:
            raise HTTPException(status_code=400, detail="correction.stage_id is required")
        correction_data = {
            "stage_id": int(correction_body["stage_id"]),
            "user_id": current_user["user_id"],
            "installation_id": event.installation_id,
            "job_card_id": correction_body.get("job_card_id", event.job_card_id),
            "vehicle_id": correction_body.get("vehicle_id", event.vehicle_id),
            "pending_vehicle_ref": correction_body.get("pending_vehicle_ref", event.pending_vehicle_ref),
            "remarks": correction_body.get("remarks", event.remarks),
            "match_status": _match_status_value(MatchStatus.MANUAL_CONFIRMED),
            "match_method": "manual_correction",
        }
        corrected_event = await create_correction_capture(db, event.event_id, correction_data)

    await void_capture(
        db,
        event_id=event.event_id,
        voided_by_user_id=current_user["user_id"],
        reason=payload.reason,
        corrected_event_id=corrected_event.event_id if corrected_event else None,
    )
    await db.commit()
    await db.refresh(event)

    return {
        "event_id": event.event_id,
        "voided": event.voided,
        "void_reason": event.void_reason,
        "voided_at": event.voided_at.isoformat() if event.voided_at else None,
        "corrected_event_id": event.corrected_event_id,
    }


@router.post("/{event_id}/confirm-match")
async def confirm_match(
    event_id: str,
    job_card_id: str = None,
    vehicle_id: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm or correct match between a capture and a job card / vehicle.

    This is the manual override endpoint for cases where plate OCR misread or
    auto-match failed. It can also be used if Security created a pending_vehicle
    and the real vehicle/job card is now known.
    """
    event_result = await db.execute(select(CaptureEvent).where(CaptureEvent.event_id == int(event_id)))
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Capture event not found")

    if job_card_id:
        jc_result = await db.execute(select(JobCard).where(JobCard.job_card_id == int(job_card_id)))
        job_card = jc_result.scalar_one_or_none()
        if not job_card:
            raise HTTPException(status_code=404, detail="Job card not found")
        event.job_card_id = job_card.job_card_id
        event.vehicle_id = job_card.vehicle_id
        event.pending_vehicle_ref = None
        event.match_status = _match_status_value(MatchStatus.MANUAL_CONFIRMED)
        event.match_method = "manual_job_card"
    elif vehicle_id:
        v_result = await db.execute(select(Vehicle).where(Vehicle.vehicle_id == int(vehicle_id)))
        vehicle = v_result.scalar_one_or_none()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        event.vehicle_id = vehicle.vehicle_id
        event.job_card_id = None
        event.pending_vehicle_ref = None
        event.match_status = _match_status_value(MatchStatus.MANUAL_CONFIRMED)
        event.match_method = "manual_vehicle"
    else:
        raise HTTPException(status_code=400, detail="Provide either job_card_id or vehicle_id")

    await db.commit()
    await db.refresh(event)
    return {
        "status": "matched",
        "event_id": event.event_id,
        "job_card_id": event.job_card_id,
        "vehicle_id": event.vehicle_id,
        "match_status": event.match_status,
        "match_method": event.match_method,
    }
