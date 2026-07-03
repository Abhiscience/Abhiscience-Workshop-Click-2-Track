#!/usr/bin/env python3
"""Apply Part B migration using SQLAlchemy metadata.

This script creates the override_requests table and the
workflow_stages.allow_override column.  It is idempotent and safe to run
against PostgreSQL or SQLite.
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
        # Ensure the table exists. For SQLite the JSON column maps to SQLite JSON;
        # for PostgreSQL/JSONB it is handled via the dialect.
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

        # Check/add allow_override column idempotently.
        def ensure_additional_columns(sync_conn):
            inspector = inspect(sync_conn)
            cols = {c["name"] for c in inspector.get_columns("workflow_stages")}
            for col_name, col_sql in (
                ("allow_override", "ALTER TABLE workflow_stages ADD COLUMN allow_override BOOLEAN NOT NULL DEFAULT TRUE"),
                ("skip_deviation", "ALTER TABLE workflow_stages ADD COLUMN skip_deviation BOOLEAN NOT NULL DEFAULT FALSE"),
            ):
                if col_name not in cols:
                    sync_conn.execute(text(col_sql))

        await conn.run_sync(ensure_additional_columns)

    await engine.dispose()
    print("Part B migration applied successfully.")


if __name__ == "__main__":
    asyncio.run(main())
