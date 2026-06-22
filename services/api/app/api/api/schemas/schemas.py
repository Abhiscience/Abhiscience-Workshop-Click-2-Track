from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# Role schemas
class RoleBase(BaseModel):
    role_name: str
    capture_label: Optional[str] = None
    permissions: Optional[dict] = Field(default_factory=dict)


class RoleCreate(RoleBase):
    pass


class RoleResponse(RoleBase):
    role_id: int
    
    class Config:
        from_attributes = True


# Branch schemas
class BranchBase(BaseModel):
    branch_name: str
    timezone: Optional[str] = "UTC"
    address: Optional[str] = None


class BranchCreate(BranchBase):
    pass


class BranchResponse(BranchBase):
    branch_id: int
    
    class Config:
        from_attributes = True


# WorkflowStage schemas
class WorkflowStageBase(BaseModel):
    branch_id: int
    stage_code: str
    stage_name: str
    sequence_order: int
    capture_mandatory: Optional[bool] = False


class WorkflowStageCreate(WorkflowStageBase):
    pass


class WorkflowStageResponse(WorkflowStageBase):
    stage_id: int
    
    class Config:
        from_attributes = True


# User schemas
class UserBase(BaseModel):
    name: str
    mobile: str
    role_id: int
    branch_id: int
    status: Optional[str] = "active"


class UserCreate(UserBase):
    password: str


class UserResponse(BaseModel):
    user_id: int
    name: str
    mobile: str
    role_id: int
    branch_id: int
    status: str
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    mobile: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# AppInstallation schemas
class AppInstallationBase(BaseModel):
    device_model: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    push_token: Optional[str] = None
    status: Optional[str] = "active"


class AppInstallationCreate(AppInstallationBase):
    user_id: int


class AppInstallationResponse(AppInstallationBase):
    installation_id: int
    user_id: int
    
    class Config:
        from_attributes = True


# Vehicle schemas
class VehicleBase(BaseModel):
    registration_number: str
    make: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    customer_id: Optional[str] = None


class VehicleCreate(VehicleBase):
    pass


class VehicleResponse(VehicleBase):
    vehicle_id: int
    
    class Config:
        from_attributes = True


# JobCard schemas
class JobCardBase(BaseModel):
    external_job_card_no: str
    vehicle_id: int
    branch_id: int
    advisor_id: Optional[int] = None
    status: Optional[str] = "open"


class JobCardCreate(JobCardBase):
    pass


class JobCardResponse(JobCardBase):
    job_card_id: int
    open_time: datetime
    close_time: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# CaptureEvent schemas
class CaptureEventBase(BaseModel):
    stage_id: int
    installation_id: int
    remarks: Optional[str] = None


class CaptureEventCreate(CaptureEventBase):
    image_url: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lng: Optional[float] = None


class CaptureEventResponse(BaseModel):
    event_id: int
    job_card_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    pending_vehicle_ref: Optional[int] = None
    stage_id: int
    user_id: int
    installation_id: int
    image_url: Optional[str] = None
    plate_text_raw: Optional[str] = None
    plate_text_normalized: Optional[str] = None
    plate_confidence: Optional[float] = None
    match_status: str
    match_method: Optional[str] = None
    captured_at_device: datetime
    received_at_server: datetime
    geo_lat: Optional[float] = None
    geo_lng: Optional[float] = None
    remarks: Optional[str] = None
    
    class Config:
        from_attributes = True


class CaptureEventConfirmMatch(BaseModel):
    job_card_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    match_method: Optional[str] = None


# PendingVehicle schemas
class PendingVehicleBase(BaseModel):
    temporary_plate_text: str
    gate_event_id: Optional[str] = None
    branch_id: int


class PendingVehicleCreate(PendingVehicleBase):
    pass


class PendingVehicleResponse(PendingVehicleBase):
    pending_vehicle_ref: int
    created_at: datetime
    link_status: str
    
    class Config:
        from_attributes = True


# Analytics schemas
class VehicleTimelineEvent(BaseModel):
    event_id: int
    stage_name: str
    plate_text: Optional[str]
    captured_at: datetime
    image_url: Optional[str]
    match_status: str


class VehicleTimeline(BaseModel):
    vehicle_id: int
    registration_number: str
    timeline: list[VehicleTimelineEvent]


class AnalyticsMetrics(BaseModel):
    gate_to_jc_open_minutes: Optional[float] = None
    jc_open_to_technician_accept_minutes: Optional[float] = None
    technician_to_parts_wait_minutes: Optional[float] = None
    parts_wait_to_parts_issue_minutes: Optional[float] = None
    wash_tat_minutes: Optional[float] = None
    qc_tat_minutes: Optional[float] = None
    total_workshop_tat_minutes: Optional[float] = None
    capture_compliance_percent: Optional[float] = None
    branch_stage_bottleneck_index: Optional[float] = None