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

ALTER TABLE workflow_stages
    ADD COLUMN IF NOT EXISTS skip_deviation BOOLEAN NOT NULL DEFAULT FALSE;

-- NOTE: is_rework was removed; rework detection is dynamic per job-card sequence.

-- Part D DDL - job_card_not_applicable_stages + CaptureEvent.voided + JobCard.cancellation_reason

CREATE TABLE IF NOT EXISTS job_card_not_applicable_stages (
    id SERIAL PRIMARY KEY,
    job_card_id INTEGER NOT NULL REFERENCES job_cards(job_card_id) ON DELETE CASCADE,
    stage_id INTEGER NOT NULL REFERENCES workflow_stages(stage_id),
    reason TEXT NOT NULL,
    marked_by_user_id INTEGER NOT NULL REFERENCES users(user_id),
    marked_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(job_card_id, stage_id)
);

CREATE INDEX IF NOT EXISTS idx_jc_na_stages_job_card
    ON job_card_not_applicable_stages(job_card_id);
CREATE INDEX IF NOT EXISTS idx_jc_na_stages_stage
    ON job_card_not_applicable_stages(stage_id);

ALTER TABLE capture_events
    ADD COLUMN IF NOT EXISTS voided BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE capture_events
    ADD COLUMN IF NOT EXISTS voided_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE capture_events
    ADD COLUMN IF NOT EXISTS voided_by INTEGER REFERENCES users(user_id);

ALTER TABLE capture_events
    ADD COLUMN IF NOT EXISTS void_reason TEXT;

ALTER TABLE capture_events
    ADD COLUMN IF NOT EXISTS corrected_event_id INTEGER REFERENCES capture_events(event_id);

ALTER TABLE job_cards
    ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;

ALTER TABLE job_cards
    ADD COLUMN IF NOT EXISTS cancellation_category_id INTEGER REFERENCES cancellation_categories(cancellation_category_id);

CREATE TABLE IF NOT EXISTS cancellation_categories (
    cancellation_category_id SERIAL PRIMARY KEY,
    branch_id INTEGER REFERENCES branches(branch_id),
    category_name VARCHAR(200) NOT NULL,
    category_code VARCHAR(50) UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_cancellation_categories_code
    ON cancellation_categories(category_code);

-- Seed default cancellation categories (idempotent).
INSERT INTO cancellation_categories (category_name, category_code, is_active) VALUES
    ('Customer refused zero bill', 'CUSTOMER_REFUSED_ZERO_BILL', TRUE),
    ('Vehicle undriveable', 'VEHICLE_UNDRIVEABLE', TRUE),
    ('Customer disputed cost', 'CUSTOMER_DISPUTED_COST', TRUE),
    ('Duplicate entry', 'DUPLICATE_ENTRY', TRUE),
    ('Other', 'OTHER', TRUE)
ON CONFLICT (category_code) DO NOTHING;
