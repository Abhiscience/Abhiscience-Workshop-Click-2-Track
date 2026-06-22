from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta

from core.database import get_db
from core.security import verify_password, create_access_token, get_password_hash
from api.schemas.schemas import UserLogin, Token, UserResponse, UserCreate, UserBase
from models.models import User, Branch, Role

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(form_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT token"""
    stmt = select(User).where(User.mobile == form_data.mobile)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid mobile or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid mobile or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active",
        )
    
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": str(user.user_id)},
        expires_delta=access_token_expires
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            user_id=user.user_id,
            name=user.name,
            mobile=user.mobile,
            role_id=user.role_id,
            branch_id=user.branch_id,
            status=user.status
        )
    )


@router.post("/register", response_model=UserResponse)
async def register(user_create: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user (admin only in production)"""
    # Check if mobile already exists
    stmt = select(User).where(User.mobile == user_create.mobile)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mobile number already registered",
        )
    
    # Verify role exists
    role_stmt = select(Role).where(Role.role_id == user_create.role_id)
    role = (await db.execute(role_stmt)).scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role ID",
        )
    
    # Verify branch exists
    branch_stmt = select(Branch).where(Branch.branch_id == user_create.branch_id)
    branch = (await db.execute(branch_stmt)).scalar_one_or_none()
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch ID",
        )
    
    user = User(
        name=user_create.name,
        mobile=user_create.mobile,
        password_hash=get_password_hash(user_create.password),
        role_id=user_create.role_id,
        branch_id=user_create.branch_id,
        status=user_create.status
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return UserResponse(
        user_id=user.user_id,
        name=user.name,
        mobile=user.mobile,
        role_id=user.role_id,
        branch_id=user.branch_id,
        status=user.status
    )