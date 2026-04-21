-- babel initial schema — mirrors SQLModel models in backend/app/models.py.
-- Generated 2026-04-21 during Phase A (cloud backend on Fly + Supabase).
--
-- Safe to run against an empty Postgres. `IF NOT EXISTS` guards everything
-- so `supabase db push` is idempotent. When the app boots it also runs
-- SQLModel.metadata.create_all(), which no-ops on existing tables.

-- ---------------- documents ----------------
CREATE TABLE IF NOT EXISTS document (
    id                      SERIAL PRIMARY KEY,
    filename                TEXT NOT NULL,
    mime_type               TEXT NOT NULL,
    size_bytes              INTEGER NOT NULL,
    page_count              INTEGER NOT NULL DEFAULT 0,
    word_count              INTEGER NOT NULL DEFAULT 0,
    token_count             INTEGER NOT NULL DEFAULT 0,
    stored_path             TEXT NOT NULL,
    detected_lang           TEXT,
    detected_lang_confidence REAL,
    uploaded_at             TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS document_uploaded_at_idx ON document (uploaded_at DESC);

-- ---------------- jobs ---------------------
CREATE TABLE IF NOT EXISTS job (
    id                  SERIAL PRIMARY KEY,
    document_id         INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'uploaded',
    source_lang         TEXT NOT NULL,
    target_lang         TEXT NOT NULL,
    model_adapter       TEXT NOT NULL,
    model_name          TEXT NOT NULL,
    chunk_count         INTEGER NOT NULL DEFAULT 0,
    translated_chunks   INTEGER NOT NULL DEFAULT 0,
    estimated_seconds   INTEGER,
    estimated_cost_usd  REAL,
    error               TEXT,
    queued_at           TIMESTAMP WITHOUT TIME ZONE,
    priority            INTEGER NOT NULL DEFAULT 0,
    submitted_by_admin  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    started_at          TIMESTAMP WITHOUT TIME ZONE,
    finished_at         TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS job_status_idx ON job (status);
CREATE INDEX IF NOT EXISTS job_document_id_idx ON job (document_id);
CREATE INDEX IF NOT EXISTS job_created_at_idx ON job (created_at DESC);

-- ---------------- chunks -------------------
CREATE TABLE IF NOT EXISTS chunk (
    id                SERIAL PRIMARY KEY,
    job_id            INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    idx               INTEGER NOT NULL,
    source_text       TEXT NOT NULL,
    translated_text   TEXT,
    reviewed_text     TEXT,
    token_count       INTEGER NOT NULL DEFAULT 0,
    translated_at     TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS chunk_job_id_idx ON chunk (job_id);
CREATE UNIQUE INDEX IF NOT EXISTS chunk_job_idx_uniq ON chunk (job_id, idx);

-- ---------------- glossary -----------------
CREATE TABLE IF NOT EXISTS glossaryterm (
    id           SERIAL PRIMARY KEY,
    job_id       INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    source_term  TEXT NOT NULL,
    target_term  TEXT,
    notes        TEXT,
    locked       BOOLEAN NOT NULL DEFAULT TRUE,
    occurrences  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS glossaryterm_job_id_idx ON glossaryterm (job_id);

-- ---------------- RLS ----------------------
-- Supabase enables RLS by default on new tables. Since all reads/writes go
-- through the FastAPI backend using the service_role key (which bypasses
-- RLS), we leave RLS disabled for now. Revisit once end-user accounts land.
ALTER TABLE document       DISABLE ROW LEVEL SECURITY;
ALTER TABLE job            DISABLE ROW LEVEL SECURITY;
ALTER TABLE chunk          DISABLE ROW LEVEL SECURITY;
ALTER TABLE glossaryterm   DISABLE ROW LEVEL SECURITY;
