"""DMS Integration Adapters - Support API, DB, File, and Webhook integrations."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import asyncio


@dataclass
class JobCardDTO:
    """Standard job card format across all DMS integrations."""
    job_card_id: str
    external_job_card_no: str
    vehicle_registration: Optional[str]
    status: str
    advisor_id: Optional[str]
    open_time: Optional[str]
    close_time: Optional[str]
    branch_id: Optional[str]
    customer_name: Optional[str]


class DMSAdapter(ABC):
    """Abstract interface for DMS system integrations."""
    
    @abstractmethod
    async def get_active_job_cards(self, branch_id: str = None) -> List[JobCardDTO]:
        """Get all active job cards from DMS."""
        pass
    
    @abstractmethod
    async def get_job_card(self, job_card_id: str) -> Optional[JobCardDTO]:
        """Get specific job card by ID."""
        pass
    
    @abstractmethod
    async def search_by_plate(self, plate_text: str) -> List[JobCardDTO]:
        """Search job cards by vehicle registration."""
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Adapter name."""
        pass


class MockDMSAdapter(DMSAdapter):
    """Mock DMS adapter for development/testing."""
    
    def __init__(self):
        self._job_cards: List[JobCardDTO] = []
    
    async def get_active_job_cards(self, branch_id: str = None) -> List[JobCardDTO]:
        # Return mock job cards
        return [
            JobCardDTO(
                job_card_id="jc_001",
                external_job_card_no="JC/2024/001",
                vehicle_registration="A12345",
                status="OPEN",
                advisor_id="user_001",
                open_time="2024-01-15T09:00:00",
                branch_id="branch_001"
            ),
            JobCardDTO(
                job_card_id="jc_002",
                external_job_card_no="JC/2024/002",
                vehicle_registration="MH01AB1234",
                status="IN_PROGRESS",
                advisor_id="user_002",
                open_time="2024-01-15T10:30:00",
                branch_id="branch_001"
            )
        ]
    
    async def get_job_card(self, job_card_id: str) -> Optional[JobCardDTO]:
        return next((jc for jc in await self.get_active_job_cards() if jc.job_card_id == job_card_id), None)
    
    async def search_by_plate(self, plate_text: str) -> List[JobCardDTO]:
        # Mock: match first digit
        return [
            jc for jc in await self.get_active_job_cards()
            if jc.vehicle_registration and plate_text[:1] == jc.vehicle_registration[:1]
        ]
    
    def name(self) -> str:
        return "mock"


def get_dms_adapter(provider: str = "mock") -> DMSAdapter:
    """Factory to get configured DMS adapter."""
    adapters = {
        "mock": MockDMSAdapter(),
        "api": MockDMSAdapter(),  # Placeholder
        "db": MockDMSAdapter(),    # Placeholder
        "file": MockDMSAdapter(),  # Placeholder
        "webhook": MockDMSAdapter(),  # Placeholder
    }
    return adapters.get(provider, MockDMSAdapter())