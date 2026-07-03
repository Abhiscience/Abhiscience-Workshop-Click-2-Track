"""Database models for Workshop Click-2-Track."""
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Float, Text, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
from datetime import datetime

Base = declarative_base()

class MatchStatus(str, enum.Enum):
    EXACT_MATCH = "EXACT_MATCH"
    NORMALIZED_MATCH = "NORMALIZED_MATCH"
    SHORTLIST_REQUIRED = "SHORTLIST_REQUIRED"
    MANUAL_CONFIRMED = "MANUAL_CONFIRMED"
    PENDING_NO_JC = "PENDING_NO_JC"
    UNMATCHED = "UNMATCHED"

class LinkStatus(str, enum.Enum):
    PENDING  = "PENDING"
    LINKED   = "LINKED"
    ORPHANED = "ORPHANED"

class OverrideRequestStatus(str, enum.Enum):
    PENDING  = "PENDING"
    APPROVED = "APPROVED"
    DENIED   = "DENIED"

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    mobile = Column(String(20), unique=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.role_id"))
    branch_id = Column(Integer, ForeignKey("branches.branch_id"))
    status = Column(String(50), default="ACTIVE")
    password_hash = Column(String(255), nullable=False)
    
    role = relationship("Role", back_populates="users")
    branch = relationship("Branch", back_populates="users")
    installations = relationship("AppInstallation", back_populates="user")

class Role(Base):
    __tablename__ = "roles"
    
    role_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    role_name = Column(String(100), nullable=False, unique=True)
    capture_label = Column(String(100))  # e.g., "Captured by Security Guard"
    permissions = Column(JSON)  # Permission set
    
    users = relationship("User", back_populates="role")

class Branch(Base):
    __tablename__ = "branches"
    
    branch_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    branch_name = Column(String(200), nullable=False)
    timezone = Column(String(50), default="Asia/Dubai")
    address = Column(Text)
    
    users = relationship("User", back_populates="branch")
    workflow_stages = relationship("WorkflowStage", back_populates="branch")
    job_cards = relationship("JobCard", back_populates="branch")

class WorkflowStage(Base):
    __tablename__ = "workflow_stages"
    
    stage_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"))
    role_id = Column(Integer, ForeignKey("roles.role_id"), nullable=True)
    stage_code = Column(String(50), nullable=False)  # GATE_ENTRY, TECH_ACCEPT, etc.
    stage_name = Column(String(200), nullable=False)
    sequence_order = Column(Integer)
    capture_mandatory = Column(Boolean, default=True)
    allow_override = Column(Boolean, default=True)
    skip_deviation = Column(Boolean, default=False)  # Part D: "not applicable" stages
    
    branch = relationship("Branch", back_populates="workflow_stages")
    role = relationship("Role")
    captures = relationship("CaptureEvent", back_populates="stage")

class JobCardNotApplicableStage(Base):
    """Per-job-card 'not applicable' stage marking (Part D)."""
    __tablename__ = "job_card_not_applicable_stages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_card_id = Column(Integer, ForeignKey("job_cards.job_card_id"), nullable=False)
    stage_id = Column(Integer, ForeignKey("workflow_stages.stage_id"), nullable=False)
    reason = Column(Text, nullable=False)
    marked_by_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    marked_at = Column(DateTime, default=datetime.utcnow)

    job_card = relationship("JobCard", back_populates="not_applicable_stages")
    stage = relationship("WorkflowStage")
    marked_by = relationship("User")

class Vehicle(Base):
    __tablename__ = "vehicles"
    
    vehicle_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    registration_number = Column(String(50), nullable=False, index=True, unique=True)
    make = Column(String(100))
    model = Column(String(100))
    color = Column(String(50))
    customer_id = Column(String(100), nullable=True)
    
    job_cards = relationship("JobCard", back_populates="vehicle")

class JobCard(Base):
    __tablename__ = "job_cards"
    
    job_card_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    external_job_card_no = Column(String(100), nullable=False, index=True, unique=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id"))
    branch_id = Column(Integer, ForeignKey("branches.branch_id"))
    advisor_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    status = Column(String(50), default="OPEN")
    cancellation_reason = Column(Text, nullable=True)
    open_time = Column(DateTime)
    close_time = Column(DateTime, nullable=True)
    
    vehicle = relationship("Vehicle", back_populates="job_cards")
    branch = relationship("Branch", back_populates="job_cards")
    advisor = relationship("User")
    capture_events = relationship("CaptureEvent", back_populates="job_card")
    not_applicable_stages = relationship("JobCardNotApplicableStage", back_populates="job_card")

class CaptureEvent(Base):
    __tablename__ = "capture_events"
    
    event_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_card_id = Column(Integer, ForeignKey("job_cards.job_card_id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id"), nullable=True)
    pending_vehicle_ref = Column(Integer, ForeignKey("pending_vehicles.pending_vehicle_ref"), nullable=True)
    
    stage_id = Column(Integer, ForeignKey("workflow_stages.stage_id"))
    user_id = Column(Integer, ForeignKey("users.user_id"))
    installation_id = Column(Integer, ForeignKey("app_installations.installation_id"))
    
    image_url = Column(String(500))
    image_hash = Column(String(255))
    plate_text_raw = Column(String(50))
    plate_text_normalized = Column(String(50))
    plate_confidence = Column(Float)
    
    match_status = Column(String(50))
    match_method = Column(String(50))  # exact, normalized, fuzzy, manual
    
    captured_at_device = Column(DateTime)
    received_at_server = Column(DateTime, default=datetime.utcnow)
    
    geo_lat = Column(Float, nullable=True)
    geo_lng = Column(Float, nullable=True)
    remarks = Column(Text, nullable=True)
    work_done_category_id = Column(Integer, ForeignKey("job_categories.job_category_id"), nullable=True)
    voided = Column(Boolean, default=False)          # Part D: correction mechanism
    voided_at = Column(DateTime, nullable=True)
    voided_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    void_reason = Column(Text, nullable=True)
    corrected_event_id = Column(Integer, ForeignKey("capture_events.event_id"), nullable=True)
    
    stage = relationship("WorkflowStage")
    user = relationship("User", foreign_keys=[user_id])
    voider = relationship("User", foreign_keys=[voided_by])
    job_card = relationship("JobCard", back_populates="capture_events")
    corrected_event = relationship("CaptureEvent", remote_side=[event_id], uselist=False)
    work_done_category = relationship("JobCategory", back_populates="captures")

class PendingVehicle(Base):
    __tablename__ = "pending_vehicles"
    
    pending_vehicle_ref = Column(Integer, primary_key=True, index=True, autoincrement=True)
    temporary_plate_text = Column(String(50), nullable=False)
    gate_event_id = Column(String(100))
    branch_id = Column(Integer, ForeignKey("branches.branch_id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    link_status = Column(String(50), default="PENDING")

class AppInstallation(Base):
    __tablename__ = "app_installations"
    
    installation_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    device_model = Column(String(100))
    os_version = Column(String(50))
    app_version = Column(String(50))
    push_token = Column(String(255), nullable=True)
    status = Column(String(50), default="ACTIVE")
    
    user = relationship("User", back_populates="installations")


class JobCategory(Base):
    __tablename__ = "job_categories"

    job_category_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=True)
    category_name = Column(String(200), nullable=False)
    category_code = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)

    captures = relationship("CaptureEvent", back_populates="work_done_category")


class OverrideRequest(Base):
    __tablename__ = "override_requests"

    override_request_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    requester_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    stage_id = Column(Integer, ForeignKey("workflow_stages.stage_id"), nullable=False)
    job_card_id = Column(Integer, ForeignKey("job_cards.job_card_id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id"), nullable=True)
    reason = Column(Text, nullable=False)
    request_data = Column(JSON, default=dict)
    status = Column(String(50), default=OverrideRequestStatus.PENDING.value)
    approved_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_event_id = Column(Integer, ForeignKey("capture_events.event_id"), nullable=True)

    requester = relationship("User", foreign_keys=[requester_user_id], backref="override_requests_requested")
    approver = relationship("User", foreign_keys=[approved_by], backref="override_requests_decided")
    stage = relationship("WorkflowStage")
    job_card = relationship("JobCard")
    vehicle = relationship("Vehicle")
    resolved_event = relationship("CaptureEvent")
