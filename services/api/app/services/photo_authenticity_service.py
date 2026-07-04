"""Photo authenticity red-flag detection for manager review queue.

These are statistical signals, not proof of fraud. They narrow down what a
human manager should physically verify; they do not automatically reject
captures or void workflow events.
"""
import hashlib
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from io import BytesIO
from PIL import Image
from PIL.ExifTags import TAGS

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload

from app.models.models import CaptureEvent, Branch, JobCard, Vehicle, WorkflowStage, User


class PhotoAuthenticityService:
    """Stateful flag calculator for a set of capture events."""

    DUPLICATE_PHOTO = "DUPLICATE_PHOTO"
    LOCATION_MISMATCH = "LOCATION_MISMATCH"
    LOCATION_MISSING = "LOCATION_MISSING"
    RAPID_FIRE_CAPTURE = "RAPID_FIRE_CAPTURE"
    STALE_PHOTO = "STALE_PHOTO"
    EXIF_MISSING = "EXIF_MISSING"

    FLAG_LABELS = {
        DUPLICATE_PHOTO: "Duplicate photo",
        LOCATION_MISMATCH: "Location outside workshop radius",
        LOCATION_MISSING: "GPS location missing",
        RAPID_FIRE_CAPTURE: "Rapid-fire captures",
        STALE_PHOTO: "EXIF timestamp much older than upload",
        EXIF_MISSING: "EXIF data missing",
    }

    STALE_THRESHOLD_HOURS = 24

    @classmethod
    async def evaluate_job_card(cls, db: AsyncSession, job_card_id: int):
        """Re-evaluate authenticity flags for all captures on a job card.

        Useful after corrections, voids, or new captures.
        """
        result = await db.execute(
            select(CaptureEvent)
            .options(
                joinedload(CaptureEvent.user),
                joinedload(CaptureEvent.stage),
            )
            .where(
                CaptureEvent.job_card_id == job_card_id,
                CaptureEvent.voided == False,
            )
            .order_by(CaptureEvent.received_at_server)
        )
        events = result.scalars().all()
        await cls.evaluate_events(db, events)

    @classmethod
    async def evaluate_events(
        cls,
        db: AsyncSession,
        events: List[CaptureEvent],
        branch_id: Optional[int] = None,
    ) -> List[CaptureEvent]:
        """Compute flags for the provided capture events.

        This clears existing flags and recomputes them for the supplied set.
        For duplicate and rapid-fire checks the caller should pass all
        relevant captures for the job or branch within the target window.
        """
        # Reset
        for event in events:
            event.authenticity_flags = []

        branch = None
        if branch_id:
            branch_result = await db.execute(
                select(Branch).where(Branch.branch_id == branch_id)
            )
            branch = branch_result.scalar_one_or_none()
        elif events:
            branch_result = await db.execute(
                select(Branch, JobCard)
                .join(JobCard, JobCard.branch_id == Branch.branch_id)
                .where(JobCard.job_card_id == events[0].job_card_id)
            )
            row = branch_result.first()
            if row:
                branch = row[0]

        # Duplicate photo detection (across the supplied set and DB)
        await cls._flag_duplicates(db, events)

        # Location flagging
        cls._flag_locations(events, branch)

        # Rapid-fire sequential captures (single-user bursts)
        cls._flag_rapid_fire(events)

        # EXIF/stale detection
        cls._flag_exif_related(events)

        return events

    # ------------------------------------------------------------------
    # 1. Duplicate photo detection
    # ------------------------------------------------------------------
    @classmethod
    async def _flag_duplicates(cls, db: AsyncSession, events: List[CaptureEvent]):
        """Flag captures sharing the same image_hash. Compare supplied events plus DB."""
        events_with_id = [e for e in events if e.event_id]
        hashes = [e.image_hash for e in events if e.image_hash]
        if not hashes:
            return

        # Detect duplicates within the supplied list.
        hash_counts: Dict[str, int] = {}
        for h in hashes:
            hash_counts[h] = hash_counts.get(h, 0) + 1
        duplicate_hashes = {h for h, count in hash_counts.items() if count > 1}

        # Compare against DB only for events that have been persisted.
        if events_with_id:
            try:
                dup_result = await db.execute(
                    select(CaptureEvent).where(
                        CaptureEvent.image_hash.in_(hashes),
                        CaptureEvent.event_id.notin_([e.event_id for e in events_with_id]),
                        CaptureEvent.voided == False,
                    )
                )
                db_dups = dup_result.scalars().all()
                for ev in db_dups:
                    if ev.image_hash:
                        duplicate_hashes.add(ev.image_hash)
            except Exception:
                pass

        for ev in events:
            if ev.image_hash in duplicate_hashes and cls.DUPLICATE_PHOTO not in ev.authenticity_flags:
                ev.authenticity_flags.append(cls.DUPLICATE_PHOTO)

    # ------------------------------------------------------------------
    # 2. GPS location flagging
    # ------------------------------------------------------------------
    @classmethod
    def _flag_locations(cls, events: List[CaptureEvent], branch: Optional[Branch]):
        if not branch or branch.workshop_geo_lat is None or branch.workshop_geo_lng is None:
            # No workshop location configured; flag missing locations only.
            for ev in events:
                if ev.geo_lat is None or ev.geo_lng is None:
                    if cls.LOCATION_MISSING not in ev.authenticity_flags:
                        ev.authenticity_flags.append(cls.LOCATION_MISSING)
            return

        radius = branch.geo_radius_meters or 200
        for ev in events:
            if ev.geo_lat is None or ev.geo_lng is None:
                if cls.LOCATION_MISSING not in ev.authenticity_flags:
                    ev.authenticity_flags.append(cls.LOCATION_MISSING)
                continue

            distance = cls._haversine(
                branch.workshop_geo_lat,
                branch.workshop_geo_lng,
                ev.geo_lat,
                ev.geo_lng,
            )
            if distance > radius:
                if cls.LOCATION_MISMATCH not in ev.authenticity_flags:
                    ev.authenticity_flags.append(cls.LOCATION_MISMATCH)

    @classmethod
    def _haversine(cls, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        R = 6371000  # Earth radius in meters
        phi1 = radians(lat1)
        phi2 = radians(lat2)
        dphi = radians(lat2 - lat1)
        dlambda = radians(lng2 - lng1)
        a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    # ------------------------------------------------------------------
    # 3. Rapid-fire sequential captures
    # ------------------------------------------------------------------
    @classmethod
    def _flag_rapid_fire(cls, events: List[CaptureEvent]):
        """Flag any user with >= 3 captures within 30 seconds."""
        window = timedelta(seconds=30)
        by_user: Dict[int, List[CaptureEvent]] = {}
        for ev in events:
            if ev.user_id is None:
                continue
            by_user.setdefault(ev.user_id, []).append(ev)

        for user_events in by_user.values():
            user_events.sort(key=lambda e: e.received_at_server or datetime.min)
            for i, ev in enumerate(user_events):
                ts = ev.received_at_server or ev.captured_at_device
                if not ts:
                    continue
                count = 1
                matched = [ev]
                for later in user_events[i + 1 :]:
                    later_ts = later.received_at_server or later.captured_at_device
                    if later_ts and later_ts - ts <= window:
                        count += 1
                        matched.append(later)
                    else:
                        break
                if count >= 3:
                    for m in matched:
                        if cls.RAPID_FIRE_CAPTURE not in m.authenticity_flags:
                            m.authenticity_flags.append(cls.RAPID_FIRE_CAPTURE)

    # ------------------------------------------------------------------
    # 4. EXIF timestamp mismatch / missing
    # ------------------------------------------------------------------
    @classmethod
    def _flag_exif_related(cls, events: List[CaptureEvent]):
        for ev in events:
            if ev.exif_missing:
                if cls.EXIF_MISSING not in ev.authenticity_flags:
                    ev.authenticity_flags.append(cls.EXIF_MISSING)
            if ev.exif_timestamp and ev.received_at_server:
                delta = abs((ev.received_at_server - ev.exif_timestamp).total_seconds())
                if delta > cls.STALE_THRESHOLD_HOURS * 3600:
                    if cls.STALE_PHOTO not in ev.authenticity_flags:
                        ev.authenticity_flags.append(cls.STALE_PHOTO)

    # ------------------------------------------------------------------
    # Utility: extract EXIF timestamp from uploaded image bytes
    # ------------------------------------------------------------------
    @classmethod
    def extract_exif_timestamp(cls, image_bytes: bytes) -> tuple[Optional[datetime], bool]:
        """Return (exif_timestamp, exif_missing)."""
        try:
            img = Image.open(BytesIO(image_bytes))
            exif = img.getexif() or {}
            if not exif:
                # Legacy fallback for older Pillow versions
                try:
                    exif = getattr(img, "_getexif", lambda: {})() or {}
                except Exception:
                    exif = {}
            if not exif:
                return None, True
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag in ("DateTime", "DateTimeOriginal", "DateTimeDigitized"):
                    try:
                        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S"), False
                    except ValueError:
                        continue
            return None, False
        except Exception:
            return None, True
