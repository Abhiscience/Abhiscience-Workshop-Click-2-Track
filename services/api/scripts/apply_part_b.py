#!/usr/bin/env python3
"""Apply Part B/D/E/F/G migration using SQLAlchemy metadata.

Creates override_requests, job_card_not_applicable_stages, cancellation_categories,
frt_catalog, job_card_job_types tables, and adds any missing columns. Idempotent.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
from app.models.models import Base, OverrideRequest


async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

        def ensure_additional_columns(sync_conn):
            inspector = inspect(sync_conn)

            # workflow_stages
            cols = {c["name"] for c in inspector.get_columns("workflow_stages")}
            for col_name, col_sql in (
                ("allow_override", "ALTER TABLE workflow_stages ADD COLUMN allow_override BOOLEAN NOT NULL DEFAULT TRUE"),
                ("skip_deviation", "ALTER TABLE workflow_stages ADD COLUMN skip_deviation BOOLEAN NOT NULL DEFAULT FALSE"),
            ):
                if col_name not in cols:
                    sync_conn.execute(text(col_sql))

            # capture_events (Part D correction mechanism + Part E parts-wait)
            ce_cols = {c["name"] for c in inspector.get_columns("capture_events")}
            for col_name, col_sql in (
                ("voided", "ALTER TABLE capture_events ADD COLUMN voided BOOLEAN NOT NULL DEFAULT FALSE"),
                ("voided_at", "ALTER TABLE capture_events ADD COLUMN voided_at TIMESTAMP WITHOUT TIME ZONE"),
                ("voided_by", "ALTER TABLE capture_events ADD COLUMN voided_by INTEGER REFERENCES users(user_id)"),
                ("void_reason", "ALTER TABLE capture_events ADD COLUMN void_reason TEXT"),
                ("corrected_event_id", "ALTER TABLE capture_events ADD COLUMN corrected_event_id INTEGER REFERENCES capture_events(event_id)"),
                ("parts_wait", "ALTER TABLE capture_events ADD COLUMN parts_wait BOOLEAN NOT NULL DEFAULT FALSE"),
                ("parts_wait_remark", "ALTER TABLE capture_events ADD COLUMN parts_wait_remark TEXT"),
            ):
                if col_name not in ce_cols:
                    sync_conn.execute(text(col_sql))

            # Part G: capture authenticity signal columns.
            if "exif_timestamp" not in ce_cols:
                sync_conn.execute(text("ALTER TABLE capture_events ADD COLUMN exif_timestamp TIMESTAMP WITHOUT TIME ZONE"))
            if "exif_missing" not in ce_cols:
                sync_conn.execute(text("ALTER TABLE capture_events ADD COLUMN exif_missing BOOLEAN NOT NULL DEFAULT FALSE"))
            if "authenticity_flags" not in ce_cols:
                sync_conn.execute(text("ALTER TABLE capture_events ADD COLUMN authenticity_flags JSONB NOT NULL DEFAULT '[]'"))

            # Part G: branch workshop geofence columns.
            branch_cols = {c["name"] for c in inspector.get_columns("branches")}
            if "workshop_geo_lat" not in branch_cols:
                sync_conn.execute(text("ALTER TABLE branches ADD COLUMN workshop_geo_lat DOUBLE PRECISION"))
            if "workshop_geo_lng" not in branch_cols:
                sync_conn.execute(text("ALTER TABLE branches ADD COLUMN workshop_geo_lng DOUBLE PRECISION"))
            if "geo_radius_meters" not in branch_cols:
                sync_conn.execute(text("ALTER TABLE branches ADD COLUMN geo_radius_meters INTEGER NOT NULL DEFAULT 200"))

            # job_cards (Part D cancellation reason + category)
            jc_cols = {c["name"] for c in inspector.get_columns("job_cards")}
            if "cancellation_reason" not in jc_cols:
                sync_conn.execute(text("ALTER TABLE job_cards ADD COLUMN cancellation_reason TEXT"))
            if "cancellation_category_id" not in jc_cols:
                sync_conn.execute(text("ALTER TABLE job_cards ADD COLUMN cancellation_category_id INTEGER REFERENCES cancellation_categories(cancellation_category_id)"))

            # Part F: staff targets, shifts, demo revenue.
            sync_conn.execute(text("""
                CREATE TABLE IF NOT EXISTS staff_targets (
                    staff_target_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    branch_id INTEGER REFERENCES branches(branch_id) ON DELETE SET NULL,
                    target_year INTEGER NOT NULL,
                    target_month INTEGER NOT NULL,
                    vehicle_target_count INTEGER,
                    daily_vehicle_target_count INTEGER,
                    monthly_revenue_target NUMERIC(12,2),
                    created_by_user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                    UNIQUE(user_id, target_year, target_month, branch_id)
                )
            """))
            sync_conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_shifts (
                    user_shift_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    branch_id INTEGER REFERENCES branches(branch_id) ON DELETE SET NULL,
                    shift_date DATE NOT NULL,
                    shift_start TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                    shift_end TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                    break_minutes INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
                )
            """))
            sync_conn.execute(text("""
                CREATE TABLE IF NOT EXISTS demo_revenue_entries (
                    demo_revenue_id SERIAL PRIMARY KEY,
                    external_job_card_no VARCHAR(100),
                    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
                    branch_id INTEGER REFERENCES branches(branch_id) ON DELETE SET NULL,
                    revenue_amount NUMERIC(12,2) NOT NULL,
                    revenue_currency VARCHAR(10) NOT NULL DEFAULT 'INR',
                    revenue_date DATE NOT NULL,
                    notes TEXT NOT NULL DEFAULT 'DEMO DATA',
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
                )
            """))

            # Part E: ensure target_time_minutes column on frt_catalog exists
            # if the table was created from metadata, this is a no-op.
            frt_cols = {c["name"] for c in inspector.get_columns("frt_catalog")}
            if "target_time_minutes" not in frt_cols:
                sync_conn.execute(text("ALTER TABLE frt_catalog ADD COLUMN target_time_minutes INTEGER NOT NULL DEFAULT 60"))

        await conn.run_sync(ensure_additional_columns)

    await engine.dispose()
    print("Part B/D/E/F/G migration applied successfully.")


if __name__ == "__main__":
    asyncio.run(main())
