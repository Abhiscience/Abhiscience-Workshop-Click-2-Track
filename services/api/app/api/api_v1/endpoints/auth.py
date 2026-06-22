"""Authentication endpoints."""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import authenticate_user, create_access_token
from app.schemas.schemas import LoginRequest, Token

router = APIRouter()

@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return JWT token."""
    # Placeholder - will use actual user lookup
    user = await authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(
        data={"sub": user.user_id},
        expires_delta=timedelta(minutes=1440)  # 24 hours
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
        "role": user.role
    }

@router.get("/me")
async def read_users_me(token: str = Depends()):
    """Get current user info."""
    return {"message": "User info endpoint"}