"""Authentication endpoints."""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.core.security import authenticate_user, create_access_token, get_current_user
from app.models.models import User
from app.schemas.schemas import LoginRequest, Token

router = APIRouter()

@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return JWT token."""
    user = await authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(
        data={"sub": str(user.user_id)},
        expires_delta=timedelta(minutes=1440)  # 24 hours
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "role_id": user.role_id
    }

@router.get("/me")
async def read_users_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Return the current authenticated user including branch_id."""
    result = await db.execute(select(User).where(User.user_id == current_user["user_id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": user.user_id,
        "name": user.name,
        "mobile": user.mobile,
        "role_id": user.role_id,
        "branch_id": user.branch_id,
        "status": user.status,
    }
