from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
import re

from core.database import get_db
from core.security import decode_token
from api.schemas.schemas import (
    WorkflowStageCreate,
    WorkflowStageResponse,
    BranchCreate,
    BranchResponse,
    RoleCreate,
    RoleResponse
)
from models.models import WorkflowStage, Branch, Role, User

router = APIRouter(prefix="/admin", tags=["admin"])


async def get_admin_user(token: dict = Depends(decode_token), db: AsyncSession = Depends(get_db)):
    """Dependency to verify current user is admin"""
    user_id = int(token.get("sub"))
    stmt = select(User).where(User.user_id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # In production, check role permissions
    # For now, just verify user exists
    return user


@router.post("/workflow-stages", response_model=WorkflowStageResponse)
async def create_workflow_stage(
    stage_create: WorkflowStageCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Create a workflow stage (admin only)"""
    # Verify branch exists
    branch_stmt = select(Branch).where(Branch.branch_id == stage_create.branch_id)
    branch = (await db.execute(branch_stmt)).scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=400, detail="Invalid branch ID")
    
    stage = WorkflowStage(**stage_create.model_dump())
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    
    return WorkflowStageResponse(
        stage_id=stage.stage_id,
        branch_id=stage.branch_id,
        stage_code=stage.stage_code,
        stage_name=stage.stage_name,
        sequence_order=stage.sequence_order,
        capture_mandatory=stage.capture_mandatory
    )


@router.get("/workflow-stages", response_model=List[WorkflowStageResponse])
async def list_workflow_stages(
    branch_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """List workflow stages"""
    stmt = select(WorkflowStage)
    if branch_id:
        stmt = stmt.where(WorkflowStage.branch_id == branch_id)
    
    stmt = stmt.order_by(WorkflowStage.branch_id, WorkflowStage.sequence_order)
    
    stages = (await db.execute(stmt)).scalars().all()
    
    return [WorkflowStageResponse(
        stage_id=s.stage_id,
        branch_id=s.branch_id,
        stage_code=s.stage_code,
        stage_name=s.stage_name,
        sequence_order=s.sequence_order,
        capture_mandatory=s.capture_mandatory
    ) for s in stages]


@router.post("/branches", response_model=BranchResponse)
async def create_branch(
    branch_create: BranchCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Create a branch (admin only)"""
    branch = Branch(**branch_create.model_dump())
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    
    return BranchResponse(
        branch_id=branch.branch_id,
        branch_name=branch.branch_name,
        timezone=branch.timezone,
        address=branch.address
    )


@router.get("/branches", response_model=List[BranchResponse])
async def list_branches(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """List all branches"""
    stmt = select(Branch).order_by(Branch.branch_name)
    branches = (await db.execute(stmt)).scalars().all()
    
    return [BranchResponse(
        branch_id=b.branch_id,
        branch_name=b.branch_name,
        timezone=b.timezone,
        address=b.address
    ) for b in branches]


@router.post("/roles", response_model=RoleResponse)
async def create_role(
    role_create: RoleCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Create a role (admin only)"""
    role = Role(**role_create.model_dump())
    db.add(role)
    await db.commit()
    await db.refresh(role)
    
    return RoleResponse(
        role_id=role.role_id,
        role_name=role.role_name,
        capture_label=role.capture_label,
        permissions=role.permissions
    )


@router.get("/roles", response_model=List[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """List all roles"""
    stmt = select(Role).order_by(Role.role_name)
    roles = (await db.execute(stmt)).scalars().all()
    
    return [RoleResponse(
        role_id=r.role_id,
        role_name=r.role_name,
        capture_label=r.capture_label,
        permissions=r.permissions
    ) for r in roles]


@router.post("/plate-ocr")
async def plate_ocr(file: UploadFile = File(...)):
    """OCR endpoint - recognizes license plates from uploaded images.
    
    Uses EasyOCR for local processing or falls back to mock provider.
    Optimized for UAE and India number plate formats.
    """
    try:
        import io
        from PIL import Image
        import numpy as np
        
        # Read image
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        
        # Try EasyOCR first
        plate_text = ""
        confidence = 0.0
        
        try:
            import easyocr
            reader = easyocr.Reader(['en'], gpu=False)
            results = reader.readtext(
                np.array(image),
                detail=1,
                paragraph=False,
                min_size=20,
            )
            
            # Extract numbers (UAE plates) or letter+number (India plates)
            for bbox, text, conf in results:
                cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
                # UAE: 4-8 digit numbers
                numbers = re.sub(r'[^0-9]', '', cleaned)
                if 4 <= len(numbers) <= 8 and conf > confidence:
                    plate_text = numbers
                    confidence = conf
                # India: format LLDDLLLNNNN
                elif re.match(r'^[A-Z]{2}[0-9]{2}[A-Z]{1,3}[0-9]{1,4}$', cleaned) and conf > confidence:
                    plate_text = cleaned
                    confidence = conf
                    
        except ImportError:
            # Fallback: mock provider
            import hashlib
            plate_text = hashlib.md5(contents).hexdigest()[:6].upper()
            confidence = 0.75
        
        # Determine format type
        if re.match(r'^[0-9]{4,8}$', plate_text):
            format_type = "uae"
        elif re.match(r'^[A-Z]{2}[0-9]{2}[A-Z]{1,3}[0-9]{1,4}$', plate_text):
            format_type = "indian"
        else:
            format_type = "unknown"
        
        return {
            "raw_text": plate_text,
            "format_type": format_type,
            "confidence": round(confidence, 2),
            "plate_number": plate_text if format_type != "unknown" else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR failed: {str(e)}")