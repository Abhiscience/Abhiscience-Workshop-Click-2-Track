"""API Router - All endpoints for Workshop Click-2-Track."""
from fastapi import APIRouter
from app.api.api_v1.endpoints import auth, captures, job_cards, analytics, admin

api_router = APIRouter()

# Authentication
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Capture events
api_router.include_router(captures.router, prefix="/captures", tags=["captures"])

# Job cards
api_router.include_router(job_cards.router, prefix="/job-cards", tags=["job-cards"])

# Analytics
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

# Admin
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])