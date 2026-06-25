import enum
from app.models.models.models import (
    Base,
    Role,
    Branch,
    WorkflowStage,
    User,
    AppInstallation,
    Vehicle,
    JobCard,
    CaptureEvent,
    PendingVehicle,
)

class MatchStatus(str, enum.Enum):
    EXACT_MATCH       = "EXACT_MATCH"
    NORMALIZED_MATCH  = "NORMALIZED_MATCH"
    SHORTLIST_REQUIRED= "SHORTLIST_REQUIRED"
    MANUAL_CONFIRMED  = "MANUAL_CONFIRMED"
    PENDING_NO_JC     = "PENDING_NO_JC"
    UNMATCHED         = "UNMATCHED"

class LinkStatus(str, enum.Enum):
    PENDING  = "PENDING"
    LINKED   = "LINKED"
    ORPHANED = "ORPHANED"
