from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/vehicle_capture"
    
    # Security
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # ANPR Provider
    ANPR_PROVIDER: str = "mock"  # mock, openalpr, platerecognizer
    ANPR_API_KEY: Optional[str] = None
    ANPR_API_URL: Optional[str] = None
    
    # App
    APP_NAME: str = "Vehicle Capture API"
    DEBUG: bool = True
    
    class Config:
        env_file = ".env"


settings = Settings()