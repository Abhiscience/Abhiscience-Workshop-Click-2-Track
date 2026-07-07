"""DMS integration provider.

Mirrors the ANPR provider pattern. The DMS provider is intentionally a narrow
interface: a DMS normally owns repair order cost, parts, labour and invoice data.
For Workshop Click-2-Track the first useful integration is pulling a small,
read-only financial summary per completed job card so that reporting dashboards
can show real revenue once a live DMS is connected.

When a real DMS is selected (e.g. Reynolds & Reynolds, CDK, ERA, etc.), only the
concrete provider implementation needs to change; the interface and factory stay
exactly the same.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class DMSBillingInfo:
    """Lightweight, old-compatible reconciliation result returned by providers.

    This is intentionally a simple class (not a Pydantic model) so it can be used
    with attribute access `billing.dms_status` / `billing.bill_amount` from the
    reconcile-dms endpoint without adding a heavy import graph.
    """

    def __init__(
        self,
        dms_status: str,  # BILLED, ZERO_BILLED, CANCELLED, NOT_FOUND, ERROR
        bill_amount: float,
        currency: str = "INR",
        summary: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.dms_status = dms_status
        self.bill_amount = bill_amount
        self.currency = currency
        self.summary = summary or {}
        self.error = error


class DMSProvider(ABC):
    """Abstract base class for Dealer Management System providers."""

    @abstractmethod
    async def get_job_financial_summary(
        self,
        external_job_card_no: Optional[str] = None,
        job_card_id: Optional[int] = None,
        vehicle_registration: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return a financial summary for a job card / repair order.

        Expected return shape (provider implementations should fill in every key):
        {
            "external_job_card_no": str | None,
            "job_card_id": int | None,
            "found": bool,
            "provider": str,
            "invoice_amount": float | None,    # billed to customer
            "labour_cost": float | None,       # cost of labour
            "parts_cost": float | None,
            "misc_cost": float | None,
            "profit_amount": float | None,     # invoice - costs (if available)
            "currency": str | None,
            "invoice_date": str | None,        # ISO date
            "error": str | None,
        }
        """
        pass

    @abstractmethod
    async def lookup_billing_info(self, external_job_card_no: str) -> DMSBillingInfo:
        """Return the legacy reconciliation billing info for a job card.

        This method supports the reconcile-dms endpoint. The mock provider uses
        the suffix convention `-Z` (zero-billed) and `-C` (cancelled) so QA can
        simulate both DMS outcomes without a real DMS connection.

        Real providers should derive dms_status and bill_amount from their own
        financial/ro data and return a `DMSBillingInfo` object.
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass


class MockDMSProvider(DMSProvider):
    """Mock DMS provider for development and demonstration.

    Returns plausible placeholder figures so the dashboard can visualise the
    shape of the data without a live DMS connection. All values are clearly
    labeled with "mock" in the provider field.

    Reconciliation test convention:
        - job card numbers ending in -Z => DMS_BILLING(BILLED, 0.0)   => ZERO_BILLED
        - job card numbers ending in -C => DMS_BILLING(CANCELLED, 0.0) => CANCELLED
        - everything else             => DMS_BILLING(BILLED, nonzero)
    """

    def __init__(self, seed: int = 1):
        self._seed = seed
        self._call_count = 0

    async def get_job_financial_summary(
        self,
        external_job_card_no: Optional[str] = None,
        job_card_id: Optional[int] = None,
        vehicle_registration: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._call_count += 1
        # Deterministic but varying placeholder numbers based on inputs.
        key = external_job_card_no or str(job_card_id or vehicle_registration or "unknown")
        hash_ = sum(ord(c) for c in key) if key else 0
        invoice = round(2500.0 + ((hash_ % 100) * 50.0) + (self._call_count % 5) * 100.0, 2)
        costs = round(invoice * 0.75, 2)
        return {
            "external_job_card_no": external_job_card_no,
            "job_card_id": job_card_id,
            "found": True,
            "provider": "mock",
            "invoice_amount": invoice,
            "labour_cost": round(costs * 0.55, 2),
            "parts_cost": round(costs * 0.35, 2),
            "misc_cost": round(costs * 0.10, 2),
            "profit_amount": round(invoice - costs, 2),
            "currency": "INR",
            "invoice_date": None,
            "error": None,
        }

    async def lookup_billing_info(self, external_job_card_no: str) -> DMSBillingInfo:
        if external_job_card_no.upper().endswith("-Z"):
            summary = await self.get_job_financial_summary(external_job_card_no=external_job_card_no)
            summary["invoice_amount"] = 0.0
            summary["profit_amount"] = 0.0
            return DMSBillingInfo(
                dms_status="BILLED",
                bill_amount=0.0,
                currency=summary.get("currency", "INR"),
                summary=summary,
            )
        if external_job_card_no.upper().endswith("-C"):
            summary = await self.get_job_financial_summary(external_job_card_no=external_job_card_no)
            return DMSBillingInfo(
                dms_status="CANCELLED",
                bill_amount=0.0,
                currency=summary.get("currency", "INR"),
                summary=summary,
            )

        # Any non-test number is treated as a normal bill.
        summary = await self.get_job_financial_summary(external_job_card_no=external_job_card_no)
        return DMSBillingInfo(
            dms_status="BILLED",
            bill_amount=summary.get("invoice_amount") or 0.0,
            currency=summary.get("currency", "INR"),
            summary=summary,
        )

    def get_provider_name(self) -> str:
        return "mock"


class ReynoldsDMSProvider(DMSProvider):
    """Stub for Reynolds & Reynolds Certified Interface (RCI) integration.

    This is intentionally unimplemented. Once the business decision is made and
    API credentials/partnership are available, fill in the authentication and
    endpoint calls here. No callers need to change.
    """

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        self.api_url = (api_url or "").rstrip("/")
        self.api_key = api_key

    async def get_job_financial_summary(
        self,
        external_job_card_no: Optional[str] = None,
        job_card_id: Optional[int] = None,
        vehicle_registration: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "external_job_card_no": external_job_card_no,
            "job_card_id": job_card_id,
            "found": False,
            "provider": "reynolds",
            "invoice_amount": None,
            "labour_cost": None,
            "parts_cost": None,
            "misc_cost": None,
            "profit_amount": None,
            "currency": None,
            "invoice_date": None,
            "error": "Reynolds DMS integration not yet implemented.",
        }

    async def lookup_billing_info(self, external_job_card_no: str) -> DMSBillingInfo:
        # Future real provider: implement DMS-specific mapping here.
        return DMSBillingInfo(
            dms_status="NOT_FOUND",
            bill_amount=0.0,
            error="Reynolds DMS billing lookup not yet implemented.",
        )

    def get_provider_name(self) -> str:
        return "reynolds"


def get_dms_provider(provider_name: str = "mock", **kwargs) -> DMSProvider:
    """Factory function for DMS providers."""
    providers = {
        "mock": MockDMSProvider,
        "reynolds": ReynoldsDMSProvider,
    }

    if provider_name not in providers:
        raise ValueError(f"Unknown DMS provider: {provider_name}")

    return providers[provider_name](**kwargs)


# Global provider instance, initialised lazily from settings.
_current_provider: Optional[DMSProvider] = None


def get_current_dms_provider() -> DMSProvider:
    """Return the configured DMS provider singleton."""
    global _current_provider
    if _current_provider is None:
        from app.core.config import settings
        kwargs = {}
        if settings.DMS_API_URL:
            kwargs["api_url"] = settings.DMS_API_URL
        if settings.DMS_API_KEY:
            kwargs["api_key"] = settings.DMS_API_KEY
        _current_provider = get_dms_provider(settings.DMS_PROVIDER, **kwargs)
    return _current_provider


def set_dms_provider(provider: DMSProvider) -> None:
    """Set (or swap) the global DMS provider. Useful for testing."""
    global _current_provider
    _current_provider = provider


async def get_job_financial_summary(
    external_job_card_no: Optional[str] = None,
    job_card_id: Optional[int] = None,
    vehicle_registration: Optional[str] = None,
) -> Dict[str, Any]:
    """Singleton access to DMS financial summary lookup."""
    provider = get_current_dms_provider()
    return await provider.get_job_financial_summary(
        external_job_card_no=external_job_card_no,
        job_card_id=job_card_id,
        vehicle_registration=vehicle_registration,
    )
