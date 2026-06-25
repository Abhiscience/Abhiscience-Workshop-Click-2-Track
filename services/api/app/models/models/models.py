from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, JSON, Float, Text, func
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import uuid
from datetime import datetime
from typing import Optional

Base = declarative_base()


class Role(Base):
    __tablename__ = "roles"
    
    role_id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(100), nullable=False, unique=True)
    capture_label = Column(String(100))
    permissions = Column(JSON, default=dict)
    
    users = relationship("User", back_populates="role")
    workflow_stages = relationship("WorkflowStage", back_populates="role")


class Branch(Base):
    __tablename__ = "branches"
    
    branch_id = Column(Integer, primary_key=True, autoincrement=True)
    branch_name = Column(String(200), nullable=False)
    timezone = Column(String(50), default="UTC")
    address = Column(Text)
    
    users = relationship("User", back_populates="branch")
    workflow_stages = relationship("WorkflowStage", back_populates="branch")
    job_cards = relationship("JobCard", back_populates="branch")
    pending_vehicles = relationship("PendingVehicle", back_populates="branch")


class WorkflowStage(Base):
    __tablename__ = "workflow_stages"
    
    stage_id = Column(Integer, primary_key=True, autoincrement=True)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=False)
    stage_code = Column(String(50), nullable=False)
    stage_name = Column(String(200), nullable=False)
    sequence_order = Column(Integer, nullable=False)
    capture_mandatory = Column(Boolean, default=False)
    role_id = Column(Integer, ForeignKey("roles.role_id"), nullable=True)
    
    branch = relationship("Branch", back_populates="workflow_stages")
    role = relationship("Role", back_populates="workflow_stages", uselist=False)
    capture_events = relationship("CaptureEvent", back_populates="stage")


class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    mobile = Column(String(20), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.role_id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=False)
    status = Column(String(50), default="active")
    
    role = relationship("Role", back_populates="users")
    branch = relationship("Branch", back_populates="users")
    app_installations = relationship("AppInstallation", back_populates="user")
    capture_events = relationship("CaptureEvent", back_populates="user")


class AppInstallation(Base):
    __tablename__ = "app_installations"
    
    installation_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    device_model = Column(String(100))
    os_version = Column(String(50))
    app_version = Column(String(50))
    push_token = Column(String(255))
    status = Column(String(50), default="active")
    
    user = relationship("User", back_populates="app_installations")
    capture_events = relationship("CaptureEvent", back_populates="installation")


class Vehicle(Base):
    __tablename__ = "vehicles"
    
    vehicle_id = Column(Integer, primary_key=True, autoincrement=True)
    registration_number = Column(String(50), nullable=False, unique=True)
    make = Column(String(100))
    model = Column(String(100))
    color = Column(String(50))
    customer_id = Column(String(100))
    
    job_cards = relationship("JobCard", back_populates="vehicle")
    capture_events = relationship("CaptureEvent", back_populates="vehicle")


class JobCard(Base):
    __tablename__ = "job_cards"
    
    job_card_id = Column(Integer, primary_key=True, autoincrement=True)
    external_job_card_no = Column(String(100), nullable=False, unique=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=False)
    advisor_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    status = Column(String(50), default="open")
    open_time = Column(DateTime, default=datetime.utcnow)
    close_time = Column(DateTime, nullable=True)
    
    vehicle = relationship("Vehicle", back_populates="job_cards")
    branch = relationship("Branch", back_populates="job_cards")
    advisor = relationship("User", back_populates="job_cards", uselist=False)
    capture_events = relationship("CaptureEvent", back_populates="job_card")


# Add back-reference to User for JobCard.advisor
User.job_cards = relationship("JobCard", back_populates="advisor", uselist=False)


class CaptureEvent(Base):
    __tablename__ = "capture_events"
    
    event_id = Column(Integer, primary_key=True, autoincrement=True)
    job_card_id = Column(Integer, ForeignKey("job_cards.job_card_id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id"), nullable=True)
    pending_vehicle_ref = Column(Integer, ForeignKey("pending_vehicles.pending_vehicle_ref"), nullable=True)
    stage_id = Column(Integer, ForeignKey("workflow_stages.stage_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    installation_id = Column(Integer, ForeignKey("app_installations.installation_id"), nullable=False)
    image_url = Column(String(500))
    image_hash = Column(String(255))
    plate_text_raw = Column(String(50))
    plate_text_normalized = Column(String(50))
    plate_confidence = Column(Float)
    match_status = Column(String(50), default="UNMATCHED")
    match_method = Column(String(50))
    captured_at_device = Column(DateTime, default=datetime.utcnow)
    received_at_server = Column(DateTime, default=datetime.utcnow)
    geo_lat = Column(Float, nullable=True)
    geo_lng = Column(Float, nullable=True)
    remarks = Column(Text, nullable=True)
    
    job_card = relationship("JobCard", back_populates="capture_events")
    vehicle = relationship("Vehicle", back_populates="capture_events")
    pending_vehicle = relationship("PendingVehicle", back_populates="capture_event")
    stage = relationship("WorkflowStage", back_populates="capture_events")
    user = relationship("User", back_populates="capture_events")
    installation = relationship("AppInstallation", back_populates="capture_events")


class PendingVehicle(Base):
    __tablename__ = "pending_vehicles"
    
    pending_vehicle_ref = Column(Integer, primary_key=True, autoincrement=True)
    temporary_plate_text = Column(String(50), nullable=False)
    gate_event_id = Column(String(100))
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    link_status = Column(String(50), default="PENDING_NO_JC")
    
    branch = relationship("Branch", back_populates="pending_vehicles")
    capture_event = relationship("CaptureEvent", back_populates="pending_vehicle", uselist=False)