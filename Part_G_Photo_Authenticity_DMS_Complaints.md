# Part G — Photo Authenticity, DMS Future-Proofing, and Complaints Placeholder

**Status:** Code complete. Some features are intentionally provision-only and deferred.
**Date:** 2026-07-07

---

## 1. What was built

### 1.1 Photo authenticity / capture signals

Implemented in code:

- `CaptureEvent` model columns: `image_hash`, `exif_timestamp`, `exif_missing`, `authenticity_flags`, `geo_lat`, `geo_lng`.
- `Branch` geofence columns: `workshop_geo_lat`, `workshop_geo_lng`, `geo_radius_meters`.
- `app/services/photo_authenticity_service.py` — flag generator.
- `app/api/api_v1/endpoints/admin.py` — `GET /api/v1/admin/suspicious-captures` manager review queue.
- Flags are **review-queue signals only**; a flagged capture is never rejected automatically.

Current flags:

| Flag                | Meaning |
|---------------------|---------|
| `DUPLICATE_PHOTO`   | Same image hash reused across captures |
| `EXIF_MISSING`      | No usable EXIF timestamp on the photo |
| `STALE_PHOTO`       | EXIF timestamp differs from server-received time by a configurable threshold |
| `RAPID_FIRE`        | Same user captured multiple events faster than the configured minimum interval |
| `LOCATION_MISSING`  | Capture has no GPS coordinates |
| `OUTSIDE_WORKSHOP`  | GPS coordinates fall outside the branch geofence radius |

Configuration in `app/core/config.py`:
- `CAPTURE_RAPID_FIRE_SECONDS` (default 5)
- `CAPTURE_STALE_MINUTES` (default 30)
- `CAPTURE_GEO_RADIUS_METERS` (default 200)

### 1.2 DMS provider (provision-only)

File: `app/providers/dms_provider.py`

Pattern mirrors `app/providers/ocr_provider.py` and `app/providers/anpr_provider.py`:

- Abstract `DMSProvider` base class.
- `MockDMSProvider` — returns placeholder financial summary per job card, clearly marked `provider: "mock"`.
- `ReynoldsDMSProvider` — stub for the future Reynolds & Reynolds connection. Currently returns `found: false` and an explicit not-implemented error.
- `get_dms_provider(...)` factory and `get_current_dms_provider()` singleton.
- Reads `DMS_PROVIDER`, `DMS_API_URL`, `DMS_API_KEY` from config (already present, were unused until now).

This means adding a real DMS implementation is a drop-in change: create a provider class that implements the same interface and point `DMS_PROVIDER` at it. No architecture changes required.

### 1.3 Complaints placeholder

Implemented in code:

- `Complaint` model: `complaint_id`, `job_card_id`, `description`, `status`, `raised_by`, `created_at`, `updated_at`.
- Pydantic schemas: `ComplaintBase`, `ComplaintCreate`, `Complaint`.
- Admin endpoints under `/api/v1/admin/complaints`:
  - `POST /api/v1/admin/complaints`
  - `GET /api/v1/admin/complaints`
  - `GET /api/v1/admin/complaints/{complaint_id}`
  - `PATCH /api/v1/admin/complaints/{complaint_id}/status`
- Migration added to `scripts/migration_part_b.sql` and `scripts/apply_part_b.py`.

This is **intentionally a placeholder** — a navigation/door only. Notifications, escalation, assignment, resolution timeline, and customer-facing forms are deferred.

---

## 2. Explicitly deferred — not part of this task

### 2.1 OCR testing (number plate recognition)

- ANPR provider code exists (`app/providers/anpr_provider.py`) but has not been end-to-end tested with real number-plate images.
- Confidence thresholds, plate normalization rules, and fallback to manual shortlist need a dedicated test phase.

### 2.2 Mobile app photo-framing requirements

- Rule: full front of vehicle must be visible and the number plate must be readable.
- Implementation depends on completing and testing OCR/ANPR phase first.
- Any automatic rejection/acceptance based on framing is deferred.

### 2.3 Real DMS / Reynolds & Reynolds connection

- Requires official Reynolds Certified Interface (RCI) partnership or a third-party connector.
- This is a business/vendor decision outside engineering scope for now.
- The `dms_provider.py` architecture is ready; only the provider implementation will need to change once access is available.

### 2.4 Revenue-per-technician calculations

- Real revenue data lives in the DMS, not in this system.
- `DemoRevenueEntry` exists only for UI demos and is clearly labeled `DEMO DATA - NOT REAL REVENUE`.
- Real revenue-per-technician reports depend on the real DMS connection above.

### 2.5 Full complaints workflow

Not built in this pass:

- Customer-facing complaint creation form.
- Email / SMS / push notifications to service managers.
- Escalation rules or SLA timers.
- Assignment to staff members.
- Resolution timeline and approval flow.
- Audit trail beyond `created_at` / `updated_at`.

The current endpoints allow an admin to record a complaint and change its status. Everything else is intentionally left for a later build-out.
