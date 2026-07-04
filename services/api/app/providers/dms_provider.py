"""DMS (Dealer Management System) provider.

This module is the boundary for all billing / invoice data from the external DMS.
Currently implemented as a mock provider for development and QA. When a real DMS
connection (e.g. Reynolds, CDK, Auto/Mate) is available, replace the async
`lookup_billing_info` implementation without changing the provider surface.
"""
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class DMSBillingInfo:
    """Billing information for a single job card from the DMS."""

    external_job_card_no: str
    dms_status: str  # OPEN, CANCELLED, BILLED, CLOSED, etc.
    bill_amount: float  # Total invoice amount. 0.0 means zero-billed.
    currency: str = "INR"
    billed_at: Optional[datetime] = None
    raw_payload: Optional[dict] = None


class DMSProviderError(Exception):
    """Raised when the DMS lookup fails or returns invalid data."""
    pass


class DMSProvider:
    """Abstract boundary for DMS billing data.

    The app should never import anything else from this module.
    """

    async def lookup_billing_info(self, external_job_card_no: str) -> DMSBillingInfo:
        """Fetch billing info for a job card.

        In the mock implementation we simulate two behaviors:
        - job cards ending in "-Z" → zero-billed completed job (BILLED, 0.0)
        - job cards ending in "-C" → cancelled in DMS (CANCELLED, 0.0)
        - everything else → not found / unknown

        This is intentionally simple so QA can test the reconciliation flow.
        """
        if not external_job_card_no:
            raise DMSProviderError("external_job_card_no is required")

        # Mock behavior for QA/testing without real DMS access.
        if external_job_card_no.endswith("-Z"):
            return DMSBillingInfo(
                external_job_card_no=external_job_card_no,
                dms_status="BILLED",
                bill_amount=0.0,
                billed_at=datetime.utcnow(),
                raw_payload={"source": "mock", "reason": "zero-billed test suffix"},
            )
        if external_job_card_no.endswith("-C"):
            return DMSBillingInfo(
                external_job_card_no=external_job_card_no,
                dms_status="CANCELLED",
                bill_amount=0.0,
                billed_at=None,
                raw_payload={"source": "mock", "reason": "cancelled test suffix"},
            )

        # Default: unknown / not present in DMS mock.
        return DMSBillingInfo(
            external_job_card_no=external_job_card_no,
            dms_status="UNKNOWN",
            bill_amount=0.0,
            billed_at=None,
            raw_payload={"source": "mock", "reason": "not found"},
        )


# Module-level singleton.
_dms_provider: Optional[DMSProvider] = None


def get_dms_provider() -> DMSProvider:
    """Return the configured DMS provider."""
    global _dms_provider
    if _dms_provider is None:
        _dms_provider = DMSProvider()
    return _dms_provider
