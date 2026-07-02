"""Database models for Workshop Click-2-Track."""
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Float, Text, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
from datetime import datetime

Base = declarative_base()

class MatchStatus(str, enum):
    EXACT_MATCH = "EXACT_MATCH"
    NORMALIZED_MATCH = "NORMALIZED_MATCH"
    SHORTLIST_REQUIRED = "SHORTLIST_REQUIRED"
    MANUAL_CONFIRMED = "MANUAL_CONFIRMED"
    PENDING_NO_JC = "PENDING_NO_JC"
    UNMATCHED = "UNMATCHED"

class LinkStatus(str, enum):
    PENDING = "PENDING"
    LINKED = "LINKED"
    ORPHANED = "ORPHANED"

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    mobile = Column(String, unique=True, index=True)
    role_id = Column(String, ForeignKey("roles.role_id"))
    branch_id = Column(String, ForeignKey("branches.branch_id"))
    status = Column(String, default="ACTIVE")
    password_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    role = relationship("Role", back_populates="users")
    branch = relationship("Branch", back_populates="users")
    installations = relationship("AppInstallation", back_populates="user")

class Role(Base):
    __tablename__ = "roles"
    
    role_id = Column(String, primary_key=True, index=True)
    role_name = Column(String, nullable=False, unique=True)
    capture_label = Column(String)  # e.g., "Captured by Security Guard"
    permissions = Column(JSON)  # Permission set
    
    users = relationship("User", back_populates="role")

class Branch(Base):
    __tablename__ = "branches"
    
    branch_id = Column(String, primary_key=True, index=True)
    branch_name = Column(String, nullable=False)
    timezone = Column(String, default="Asia/Dubai")
    address = Column(Text)
    
    users = relationship("User", back_populates="branch")
    workflow_stages = relationship("WorkflowStage", back_populates="branch")

class WorkflowStage(Base):
    __tablename__ = "workflow_stages"
    
    stage_id = Column(String, primary_key=True, index=True)
    branch_id = Column(String, ForeignKey("branches.branch_id"))
    stage_code = Column(String, nullable=False)  # GATE_ENTRY, TECH_ACCEPT, etc.
    stage_name = Column(String, nullable=False)
    sequence_order = Column(Integer)
    capture_mandatory = Column(Boolean, default=True)
    
    branch = relationship("Branch", back_populates="workflow_stages")

class Vehicle(Base):
    __tablename__ = "vehicles"
    
    vehicle_id = Column(String, primary_key=True, index=True)
    registration_number = Column(String, nullable=False, index=True)
    make = Column(String)
    model = Column(String)
    color = Column(String)
    customer_id = Column(String, nullable=True)
    region = Column(String, default="UA")  # UA or IN
    
    job_cards = relationship("JobCard", back_populates="vehicle")

class JobCard(Base):
    __tablename__ = "job_cards"
    
    job_card_id = Column(String, primary_key=True, index=True)
    external_job_card_no = Column(String, nullable=False, index=True)
    vehicle_id = Column(String, ForeignKey("vehicles.vehicle_id"), nullable=True)
    branch_id = Column(String, ForeignKey("branches.branch_id"))
    advisor_id = Column(String, ForeignKey("users.user_id"), nullable=True)
    status = Column(String, default="OPEN")
    open_time = Column(DateTime)
    close_time = Column(DateTime, nullable=True)
    
    vehicle = relationship("Vehicle", back_populates="job_cards")

class CaptureEvent(Base):
    __tablename__ = "capture_events"
    
    event_id = Column(String, primary_key=True, index=True)
    job_card_id = Column(String, ForeignKey("job_cards.job_card_id"), nullable=True)
    vehicle_id = Column(String, ForeignKey("vehicles.vehicle_id"), nullable=True)
    pending_vehicle_ref = Column(String, ForeignKey("pending_vehicles.pending_vehicle_ref"), nullable=True)
    
    stage_id = Column(String, ForeignKey("workflow_stages.stage_id"))
    user_id = Column(String, ForeignKey("users.user_id"))
    installation_id = Column(String, ForeignKey("app_installations.installation_id"))
    
    image_url = Column(String)
    image_hash = Column(String)
    plate_text_raw = Column(String)
    plate_text_normalized = Column(String)
    plate_confidence = Column(Float)
    
    match_status = Column(Enum(MatchStatus))
    match_method = Column(String)  # exact, normalized, fuzzy, manual
    
    captured_at_device = Column(DateTime)
    received_at_server = Column(DateTime, default=datetime.utcnow)
    
    geo_lat = Column(Float, nullable=True)
    geo_lng = Column(Float, nullable=True)
    remarks = Column(Text, nullable=True)
    
    stage = relationship("WorkflowStage")
    user = relationship("User")

class PendingVehicle(Base):
    __tablename__ = "pending_vehicles"
    
    pending_vehicle_ref = Column(String, primary_key=True, index=True)
    temporary_plate_text = Column(String)
    gate_event_id = Column(String, ForeignKey("capture_events.event_id"), nullable=True)
    branch_id = Column(String, ForeignKey("branches.branch_id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    link_status = Column(Enum(LinkStatus), default=LinkStatus.PENDING)

class AppInstallation(Base):
    __tablename__ = "app_installations"
    
    installation_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"))
    device_model = Column(String)
    os_version = Column(String)
    app_version = Column(String)
    push_token = Column(String, nullable=True)
    status = Column(String, default="ACTIVE")
    
    user = relationship("User", back_populates="installations")