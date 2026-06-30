"""Admin management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import re
from app.providers.ocr_provider import get_ocr_provider
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decode_token
from app.core.database import get_db

router = APIRouter()

async def get_admin_user():
    return {"user_id": 1}

@router.get("/dashboard/branch-overview")
async def get_branch_overview(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get branch overview for admin."""
    return {
        "branches": [],
        "total_vehicles": 0,
        "utilization_rate": 0
    }

@router.get("/workflow-stages")
async def get_workflow_stages(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workflow stage configuration."""
    return {"stages": []}

@router.post("/workflow-stages")
async def create_workflow_stage(
    stage_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create or update workflow stage configuration."""
    return {"status": "created", "stage": stage_data}

@router.get("/users")
async def list_users(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users."""
    return {"users": []}

@router.post("/users")
async def create_user(
    user_data: dict,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new user."""
    return {"status": "created", "user": user_data}

@router.get("/audit-trail")
async def get_audit_trail(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """View audit trail of all events."""
    return {"events": []}

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
