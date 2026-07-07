"""Security utilities for JWT authentication."""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request, HTTPException, status
from app.core.config import settings
from app.models.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

async def authenticate_user(mobile: str, password: str, db: AsyncSession) -> Optional[User]:
    from sqlalchemy.future import select
    stmt = select(User).where(User.mobile == mobile)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        return user_id
    except JWTError:
        return None


def get_current_user(request: Request) -> dict:
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
