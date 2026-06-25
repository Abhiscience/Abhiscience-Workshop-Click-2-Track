"""Admin management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
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