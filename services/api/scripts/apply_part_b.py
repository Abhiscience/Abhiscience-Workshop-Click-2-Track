#!/usr/bin/env python3
"""Apply Part B/D migration using SQLAlchemy metadata.

This script creates the override_requests table, job_card_not_applicable_stages,
and any missing columns.  It is idempotent and safe to run against PostgreSQL or
SQLite (note: column-adding SQL is only executed when the column is missing).
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

            # capture_events (Part D correction mechanism)
            ce_cols = {c["name"] for c in inspector.get_columns("capture_events")}
            for col_name, col_sql in (
                ("voided", "ALTER TABLE capture_events ADD COLUMN voided BOOLEAN NOT NULL DEFAULT FALSE"),
                ("voided_at", "ALTER TABLE capture_events ADD COLUMN voided_at TIMESTAMP WITHOUT TIME ZONE"),
                ("voided_by", "ALTER TABLE capture_events ADD COLUMN voided_by INTEGER REFERENCES users(user_id)"),
                ("void_reason", "ALTER TABLE capture_events ADD COLUMN void_reason TEXT"),
                ("corrected_event_id", "ALTER TABLE capture_events ADD COLUMN corrected_event_id INTEGER REFERENCES capture_events(event_id)"),
            ):
                if col_name not in ce_cols:
                    sync_conn.execute(text(col_sql))

            # job_cards (Part D cancellation reason + category)
            jc_cols = {c["name"] for c in inspector.get_columns("job_cards")}
            if "cancellation_reason" not in jc_cols:
                sync_conn.execute(text("ALTER TABLE job_cards ADD COLUMN cancellation_reason TEXT"))
            if "cancellation_category_id" not in jc_cols:
                sync_conn.execute(text("ALTER TABLE job_cards ADD COLUMN cancellation_category_id INTEGER REFERENCES cancellation_categories(cancellation_category_id)"))

        await conn.run_sync(ensure_additional_columns)

    await engine.dispose()
    print("Part B/D migration applied successfully.")


if __name__ == "__main__":
    asyncio.run(main())
