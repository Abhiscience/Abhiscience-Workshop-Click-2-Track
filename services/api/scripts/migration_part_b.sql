# Part B DDL - override_requests table + WorkflowStage.allow_override

CREATE TABLE IF NOT EXISTS override_requests (
    override_request_id SERIAL PRIMARY KEY,
    requester_user_id INTEGER NOT NULL REFERENCES users(user_id),
    stage_id INTEGER NOT NULL REFERENCES workflow_stages(stage_id),
    job_card_id INTEGER REFERENCES job_cards(job_card_id),
    vehicle_id INTEGER REFERENCES vehicles(vehicle_id),
    reason TEXT NOT NULL,
    request_data JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    approved_by INTEGER REFERENCES users(user_id),
    decided_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    resolved_event_id INTEGER REFERENCES capture_events(event_id)
);

CREATE INDEX IF NOT EXISTS idx_override_requests_status
    ON override_requests(status);
CREATE INDEX IF NOT EXISTS idx_override_requests_requester
    ON override_requests(requester_user_id);
CREATE INDEX IF NOT EXISTS idx_override_requests_stage
    ON override_requests(stage_id);
CREATE INDEX IF NOT EXISTS idx_override_requests_created_at
    ON override_requests(created_at DESC);

-- SQLite does not support JSONB natively; use JSON column type in sqlite.
-- For PostgreSQL, JSONB is fine.  Alembic/SQLAlchemy generate JSON column as
-- JSONB on Postgres and JSON on sqlite by default.

ALTER TABLE workflow_stages
    ADD COLUMN IF NOT EXISTS allow_override BOOLEAN NOT NULL DEFAULT TRUE;
