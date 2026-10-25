-- Resume Intelligence Studio — initial schema (version 1)
-- Applied inside a transaction by ris/storage/migrations.py. Do not edit after release;
-- add a new numbered migration instead.

CREATE TABLE records (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    parent_id       TEXT REFERENCES records(id) ON DELETE CASCADE,
    sort_order      REAL NOT NULL DEFAULT 0,
    verification    TEXT NOT NULL DEFAULT 'unconfirmed'
                    CHECK (verification IN ('unconfirmed', 'confirmed', 'evidenced')),
    confidentiality TEXT NOT NULL DEFAULT 'review'
                    CHECK (confidentiality IN ('public', 'approved', 'review', 'confidential')),
    origin          TEXT NOT NULL DEFAULT 'manual'
                    CHECK (origin IN ('manual', 'imported', 'preloaded', 'sample', 'generated', 'synced')),
    data            TEXT NOT NULL CHECK (json_valid(data)),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    revision        INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    checksum        TEXT NOT NULL,
    deleted         INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
    deleted_at      TEXT,
    modified_by     TEXT NOT NULL DEFAULT '',
    CHECK (parent_id IS NULL OR parent_id <> id)
);

CREATE INDEX idx_records_kind ON records (kind, deleted, sort_order);
CREATE INDEX idx_records_parent ON records (parent_id, deleted, sort_order);
CREATE INDEX idx_records_updated ON records (updated_at);

CREATE VIRTUAL TABLE records_fts USING fts5 (
    record_id UNINDEXED,
    kind UNINDEXED,
    content,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE variant_versions (
    id               TEXT PRIMARY KEY,
    variant_id       TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    version_no       INTEGER NOT NULL CHECK (version_no >= 1),
    created_at       TEXT NOT NULL,
    label            TEXT NOT NULL DEFAULT '',
    settings         TEXT NOT NULL CHECK (json_valid(settings)),
    document         TEXT NOT NULL CHECK (json_valid(document)),
    source_revisions TEXT NOT NULL CHECK (json_valid(source_revisions)),
    template_id      TEXT NOT NULL,
    template_version TEXT NOT NULL,
    checksum         TEXT NOT NULL,
    UNIQUE (variant_id, version_no)
);

CREATE TABLE exports (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    document_kind TEXT NOT NULL CHECK (document_kind IN ('resume', 'cover_letter', 'portfolio')),
    variant_id    TEXT,
    version_id    TEXT,
    source_id     TEXT,
    format        TEXT NOT NULL CHECK (format IN ('docx', 'pdf', 'txt')),
    path          TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL CHECK (size_bytes >= 0),
    sha256        TEXT NOT NULL,
    engine        TEXT NOT NULL DEFAULT '',
    page_count    INTEGER,
    status        TEXT NOT NULL CHECK (status IN ('valid', 'warnings')),
    validation    TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(validation)),
    redacted      INTEGER NOT NULL DEFAULT 0 CHECK (redacted IN (0, 1)),
    removed       INTEGER NOT NULL DEFAULT 0 CHECK (removed IN (0, 1))
);

CREATE INDEX idx_exports_created ON exports (created_at);

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL CHECK (json_valid(value)),
    updated_at TEXT NOT NULL
);

CREATE TABLE audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    at        TEXT NOT NULL,
    action    TEXT NOT NULL,
    record_id TEXT,
    kind      TEXT,
    detail    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_audit_at ON audit_log (at);

CREATE TABLE sync_base (
    object_id TEXT PRIMARY KEY,
    revision  INTEGER NOT NULL,
    checksum  TEXT NOT NULL,
    synced_at TEXT NOT NULL
);

CREATE TABLE sync_conflicts (
    id          TEXT PRIMARY KEY,
    object_id   TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT '',
    detected_at TEXT NOT NULL,
    local       TEXT CHECK (local IS NULL OR json_valid(local)),
    remote      TEXT CHECK (remote IS NULL OR json_valid(remote)),
    status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    resolution  TEXT NOT NULL DEFAULT '',
    resolved_at TEXT
);
