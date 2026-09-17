-- Control-plane tables per Technical Design Document section 6/8:
-- policy source of truth, action approval state machine, and the
-- append-only audit trail. Empty at ingestion time; populated by the
-- (future) application layer, not the CSV loader.
SET search_path TO shopops_ops;

CREATE TABLE IF NOT EXISTS policy_documents (
    doc_id          TEXT NOT NULL,
    version         TEXT NOT NULL,
    title           TEXT,
    domain          TEXT,
    effective_from  TIMESTAMP,
    effective_to    TIMESTAMP,
    status          TEXT NOT NULL DEFAULT 'draft',
    checksum        TEXT,
    source_uri      TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (doc_id, version)
);

CREATE TABLE IF NOT EXISTS action_requests (
    action_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type      TEXT NOT NULL,
    order_id         TEXT,
    payload_hash     TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'PROPOSED'
                        CHECK (status IN ('PROPOSED', 'APPROVED', 'EXECUTING', 'SUCCEEDED', 'FAILED', 'REJECTED')),
    requested_by     TEXT NOT NULL,
    approved_by      TEXT,
    idempotency_key  TEXT NOT NULL UNIQUE,
    policy_version   TEXT,
    expires_at       TIMESTAMP,
    created_at       TIMESTAMP NOT NULL DEFAULT now(),
    updated_at       TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prev_hash       TEXT,
    occurred_at     TIMESTAMP NOT NULL DEFAULT now(),
    request_id      TEXT,
    user_id         TEXT,
    role_snapshot   TEXT,
    action_type     TEXT,
    intent          TEXT,
    tool_name       TEXT,
    arguments_hash  TEXT,
    result_hash     TEXT,
    policy_version  TEXT,
    citations       JSONB,
    approval_id     UUID,
    outcome         TEXT,
    error_code      TEXT,
    event_json      JSONB
);
CREATE INDEX IF NOT EXISTS idx_audit_events_request_id ON audit_events (request_id);

-- Append-only enforcement per section 3.3: the application role may
-- INSERT but never UPDATE/DELETE audit history.
CREATE OR REPLACE FUNCTION shopops_ops.forbid_audit_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_events_append_only ON audit_events;
CREATE TRIGGER trg_audit_events_append_only
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION shopops_ops.forbid_audit_mutation();
