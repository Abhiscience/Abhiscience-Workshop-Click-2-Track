"""Core configuration."""
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Workshop Click-2-Track"
    VERSION: str = "0.1.0"
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./workshop.db"
    SYNC_DATABASE_URL: Optional[str] = None
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    
    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Object Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "workshop-evidence"
    
    # ANPR
    ANPR_PROVIDER: str = "mock"
    PLATERECOGNIZER_API_KEY: Optional[str] = None
    
    # DMS Integration
    DMS_PROVIDER: str = "mock"
    DMS_API_URL: Optional[str] = None
    DMS_API_KEY: Optional[str] = None
    
    # Environment
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    
    class Config:
        env_file = ".env"

settings = Settings()