-- Version 1.1: exports can also be interview preparation packs and personal questionnaires.
-- SQLite cannot change a CHECK constraint in place, so the table is rebuilt with the same data.
CREATE TABLE exports_v2 (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    document_kind TEXT NOT NULL CHECK (document_kind IN ('resume', 'cover_letter', 'portfolio', 'interview_pack',
                                                         'questionnaire')),
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

INSERT INTO exports_v2 SELECT id, created_at, document_kind, variant_id, version_id, source_id, format, path,
    size_bytes, sha256, engine, page_count, status, validation, redacted, removed FROM exports;

DROP TABLE exports;

ALTER TABLE exports_v2 RENAME TO exports;

CREATE INDEX idx_exports_created ON exports (created_at);
