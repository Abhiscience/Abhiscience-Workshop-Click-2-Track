# Architecture Overview

## System Design

The Workshop Click-2-Track platform uses a **modular, integration-first architecture** that sits alongside existing DMS systems without disruption.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Android App   │────▶│    Backend      │◀────│ Existing DMS    │
│  (Kotlin/Jetpack)│     │  (FastAPI)     │     │  System         │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
  Camera Capture         Event Store              Job Cards,
       +                    +                   Parts, Billing
  Plate Recognition   Analytics Engine           (Read Only)
       +                    +
  Offline Queue         Deviation Detection
       │                    │
       ▼                    ▼
  Sync When Online    Dashboard Reports
```

## Components

### 1. Mobile App (`apps/mobile-android`)
- Role-based authentication
- Camera-first capture flow
- Offline queue with Room DB
- Plate recognition via backend API
- Job card matching and confirmation
- Stage-aware UI per role

### 2. Backend API (`services/api`)
- FastAPI with async SQLAlchemy
- PostgreSQL for core data
- Redis for caching/queues
- Pluggable ANPR providers
- DMS integration adapters
- Deviation detection engine

### 3. Admin Dashboard (`apps/admin-web`)
- Branch overview
- Live vehicle tracking
- Analytics dashboards
- Deviation reports
- User management
- Stage configuration

### 4. Integration Layer (`services/integration-adapters`)
- Adapter pattern for DMS systems
- Support for: API, DB, File, Webhook
- Configurable per branch/workshop

---

## ANPR Provider Strategy (UAE + India Support)

```python
# PlateRecognitionProvider interface
class PlateRecognitionProvider(Protocol):
    def detect_and_recognize(self, image: bytes) -> RecognitionResult:
        """
        Returns:
        - plate_text: str
        - confidence: float
        - region_hint: str (UA / IN)
        - bounding_box: dict
        """
```

### Supported Providers

| Provider | Strengths | Use Case |
|----------|-----------|----------|
| Mock Provider | Development/testing | Local dev, emulator |
| PlateRecognizer | UAE plates, good accuracy | Production (Primary) |
| EasyOCR/Custom | India plates, multilingual | Production (Alternative) |
| Hybrid | Combine multiple | Fallback/validation |

---

## Workflow Engine

Supports configurable stages per branch:

```
Gate Entry → Advisor Receipt → Technician Accept → Diagnosis
    ↓              ↓              ↓              ↓
Parts Check   Parts Issue     Parts Issue      Washing Queue
    ↓              ↓              ↓              ↓
Quality Check → Ready for Delivery → Exit
```

Each stage:
- Can have mandatory capture
- Configurable sequence
- Role-specific permissions
- Timestamp tracking
- Image evidence required

---

## Data Model

Core entities stored immutably:

- **User** - Workshop personnel with roles
- **Role** - Permission sets (Security, Advisor, Technician, etc.)
- **Branch** - Workshop location
- **Vehicle** - Registration info
- **JobCard** - Link to DMS
- **CaptureEvent** - Immutable event log
- **PendingVehicle** - Unmatched gate entries
- **AppInstallation** - Device tracking

See [Data Model](data-model.md) for full schema.