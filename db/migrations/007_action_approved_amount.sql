-- Persists the amount actually approved, so a repeated /approve call on an
-- already-SUCCEEDED action returns the receipt for what was approved -
-- not a freshly recomputed (possibly different) amount.
SET search_path TO shopops_ops;
ALTER TABLE action_requests ADD COLUMN IF NOT EXISTS approved_amount NUMERIC;
