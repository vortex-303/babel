-- Phase D0 — add owner_id to documents for per-session file isolation.
-- Legacy rows (created before this migration) have NULL owner_id and are
-- only visible to admin; real users will only see their own uploads.

ALTER TABLE document ADD COLUMN IF NOT EXISTS owner_id TEXT;
CREATE INDEX IF NOT EXISTS document_owner_id_idx ON document (owner_id);
