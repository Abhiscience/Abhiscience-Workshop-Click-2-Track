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
    PENDING = "PENDING"
    LINKED = "LINKED"
    ORPHANED = "ORPHANED"

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

class WorkflowStage(Base):
    __tablename__ = "workflow_stages"
    
    stage_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"))
    role_id = Column(Integer, ForeignKey("roles.role_id"), nullable=True)
    stage_code = Column(String(50), nullable=False)  # GATE_ENTRY, TECH_ACCEPT, etc.
    stage_name = Column(String(200), nullable=False)
    sequence_order = Column(Integer)
    capture_mandatory = Column(Boolean, default=True)
    
    branch = relationship("Branch", back_populates="workflow_stages")

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
    open_time = Column(DateTime)
    close_time = Column(DateTime, nullable=True)
    
    vehicle = relationship("Vehicle", back_populates="job_cards")

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
    
    stage = relationship("WorkflowStage")
    user = relationship("User")

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
