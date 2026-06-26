"""Pydantic schemas for API validation."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MatchStatus(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    NORMALIZED_MATCH = "NORMALIZED_MATCH"
    SHORTLIST_REQUIRED = "SHORTLIST_REQUIRED"
    MANUAL_CONFIRMED = "MANUAL_CONFIRMED"
    PENDING_NO_JC = "PENDING_NO_JC"
    UNMATCHED = "UNMATCHED"


# User schemas
class UserBase(BaseModel):
    name: str
    mobile: str

class UserCreate(UserBase):
    role_id: str
    branch_id: str

class User(UserBase):
    user_id: int
    role_id: str
    branch_id: str
    status: str

    class Config:
        from_attributes = True


# Role schemas
class RoleBase(BaseModel):
    role_name: str
    capture_label: Optional[str]

class Role(RoleBase):
    role_id: str
    permissions: dict

    class Config:
        from_attributes = True


# Vehicle schemas
class VehicleBase(BaseModel):
    registration_number: str
    make: Optional[str]
    model: Optional[str]
    color: Optional[str]
    region: Optional[str] = "UA"

class VehicleCreate(VehicleBase):
    pass

class Vehicle(VehicleBase):
    vehicle_id: str

    class Config:
        from_attributes = True


# Job Card schemas
class JobCardBase(BaseModel):
    external_job_card_no: str
    vehicle_id: Optional[str]
    branch_id: str

class JobCard(JobCardBase):
    job_card_id: str
    status: str
    open_time: Optional[datetime]
    close_time: Optional[datetime]

    class Config:
        from_attributes = True


# Capture Event schemas
class CaptureEventBase(BaseModel):
    stage_id: int
    remarks: Optional[str]

class CaptureEventCreate(CaptureEventBase):
    plate_text: Optional[str]
    confidence: Optional[float]

class CaptureEvent(CaptureEventBase):
    event_id: int
    job_card_id: Optional[str]
    vehicle_id: Optional[str]
    pending_vehicle_ref: Optional[str]
    user_id: int
    installation_id: int
    image_url: Optional[str]
    plate_text_raw: Optional[str]
    plate_text_normalized: Optional[str]
    plate_confidence: Optional[float]
    match_status: MatchStatus
    captured_at_device: Optional[datetime]
    received_at_server: Optional[datetime]

    class Config:
        from_attributes = True


# Auth schemas
class LoginRequest(BaseModel):
    mobile: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[str] = None


# Analytics schemas
class TimelineEvent(BaseModel):
    event_id: int
    stage_name: str
    stage_code: str
    user_name: str
    role_name: str
    captured_at: datetime
    image_url: Optional[str]

class VehicleTimeline(BaseModel):
    vehicle_id: str
    registration_number: str
    job_card_id: str
    events: List[TimelineEvent]

class DeviationResponse(BaseModel):
    deviation_type: str
    stage_code: str
    description: str
    expected_time: Optional[datetime]
    actual_time: Optional[datetime]
    severity: str
    details: dict

class UtilizationMetrics(BaseModel):
    gate_to_advisor_minutes: float
    advisor_to_technician_minutes: float
    total_turnaround_minutes: float
    capture_compliance_percent: float
    bottleneck_stages: List[str]