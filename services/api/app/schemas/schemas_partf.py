"""Part F reporting & staff feature schemas."""
from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel


class StaffPerformanceRow(BaseModel):
    user_id: int
    name: Optional[str]
    role_id: Optional[int]
    role_name: Optional[str]
    capture_count: int
    vehicles_handled_count: int
    cumulative_technician_minutes: float
    rework_cycles_detected: int


class StaffPerformanceByRole(BaseModel):
    role_id: Optional[int]
    role_name: Optional[str]
    user_count: int
    total_captures: int
    total_vehicles_handled: int
    total_technician_minutes: float
    users: List[StaffPerformanceRow]


class StaffPerformanceResponse(BaseModel):
    period_start: str
    period_end: str
    branch_id: Optional[int]
    per_individual: List[StaffPerformanceRow]
    per_role: List[StaffPerformanceByRole]


class VehicleFlowStage(BaseModel):
    stage_id: int
    stage_code: Optional[str]
    stage_name: Optional[str]
    role_name: Optional[str]
    vehicle_count: int
    avg_wait_minutes: float
    max_wait_minutes: float
    deviation_count: int


class VehicleFlowWorstBottleneck(BaseModel):
    stage_id: int
    stage_code: Optional[str]
    stage_name: Optional[str]
    vehicle_count: int
    avg_wait_minutes: float
    reason: Optional[str]


class VehicleFlowAtRiskAlert(BaseModel):
    job_card_id: int
    external_job_card_no: Optional[str]
    registration_number: Optional[str]
    stage_code: Optional[str]
    stage_name: Optional[str]
    target_minutes: Optional[int]
    actual_minutes: Optional[float]
    excess_minutes: float


class VehicleFlowResponse(BaseModel):
    period_start: str
    period_end: str
    branch_id: Optional[int]
    stages: List[VehicleFlowStage]
    worst_bottleneck: Optional[VehicleFlowWorstBottleneck]
    at_risk_alerts: List[VehicleFlowAtRiskAlert]
    deviation_summary_note: str


class StaffUtilizationRow(BaseModel):
    user_id: int
    name: Optional[str]
    role_name: Optional[str]
    shift_date: Optional[str]
    shift_start: Optional[str]
    shift_end: Optional[str]
    shift_minutes: float
    break_minutes: float
    available_minutes: float
    active_technician_minutes: float
    utilization_percent: float


class PartsShortagePatternItem(BaseModel):
    pattern_key: str
    count: int
    total_wait_minutes: float
    sample_remarks: List[str]


class PartsShortagePatterns(BaseModel):
    period_start: str
    period_end: str
    branch_id: Optional[int]
    total_parts_wait_events: int
    total_parts_wait_minutes: float
    top_patterns: List[PartsShortagePatternItem]


class ReworkRateTechnician(BaseModel):
    user_id: int
    name: Optional[str]
    rework_cycles: int
    total_cycles: int
    rework_rate_percent: float


class ReworkRateReport(BaseModel):
    period_start: str
    period_end: str
    branch_id: Optional[int]
    total_rework_cycles: int
    by_technician: List[ReworkRateTechnician]


class StaffTargetUpsert(BaseModel):
    branch_id: Optional[int] = None
    target_year: int
    target_month: int
    vehicle_target_count: Optional[int] = None
    daily_vehicle_target_count: Optional[int] = None
    monthly_revenue_target: Optional[float] = None


class TeamTargetUserItem(BaseModel):
    user_id: int
    name: Optional[str]
    role_id: Optional[int]
    role_name: Optional[str]
    monthly_vehicle_target: Optional[int]
    daily_vehicle_target: Optional[int]
    monthly_revenue_target: Optional[float]
    vehicles_handled_actual: int
    captures_count_actual: int
    revenue_achievement_status: str
    revenue_achievement_amount: Optional[float]
    demo_revenue_included: bool


class TeamTargetsDashboard(BaseModel):
    year: int
    month: int
    branch_id: Optional[int]
    dms_connected: bool
    demo_mode: bool
    disclaimer: str
    users: List[TeamTargetUserItem]


class AIActionPlanResponse(BaseModel):
    provider_used: str
    model: Optional[str]
    cost_note: Optional[str]
    action_plan: str
    raw_usage: Optional[dict]
    error: Optional[str]


class UserShiftCreate(BaseModel):
    user_id: int
    branch_id: Optional[int] = None
    shift_date: date
    shift_start: time
    shift_end: time
    break_minutes: int = 0


class DemoRevenueEntryCreate(BaseModel):
    external_job_card_no: Optional[str] = None
    user_id: Optional[int] = None
    branch_id: Optional[int] = None
    revenue_amount: float
    revenue_currency: Optional[str] = "INR"
    revenue_date: date

