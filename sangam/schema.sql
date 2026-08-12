-- Sangam schema (Postgres / Supabase). Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS channels (
    channel_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    handle              TEXT,
    source_type         TEXT,            -- research | educator | opinion (your tag)
    is_sebi_registered  BOOLEAN
);

CREATE TABLE IF NOT EXISTS videos (
    video_id           TEXT PRIMARY KEY,
    channel_id         TEXT NOT NULL REFERENCES channels(channel_id),
    title              TEXT,
    description        TEXT,
    url                TEXT,
    published_at       TIMESTAMPTZ,
    is_short           BOOLEAN DEFAULT FALSE,
    fetched_at         TIMESTAMPTZ DEFAULT now(),
    transcript_status  TEXT DEFAULT 'pending',   -- pending | done | none | error
    transcript_source  TEXT,                      -- captions | whisper (later)
    transcript_text    TEXT,
    summary            TEXT,                      -- filled by extraction slice
    extract_status     TEXT DEFAULT 'pending'     -- pending | done | error
);

CREATE TABLE IF NOT EXISTS mentions (
    id               BIGSERIAL PRIMARY KEY,
    video_id         TEXT NOT NULL REFERENCES videos(video_id),
    raw_mention      TEXT,
    resolved_symbol  TEXT,
    instrument_type  TEXT,             -- stock | mutual_fund | sector
    action           TEXT,             -- buy | sell | hold | wait_for_dip | radar | future_opportunity | neutral
    confidence       REAL,
    evidence         TEXT,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_videos_published    ON videos(published_at);
CREATE INDEX IF NOT EXISTS idx_videos_transcript   ON videos(transcript_status);
CREATE INDEX IF NOT EXISTS idx_mentions_symbol     ON mentions(resolved_symbol);
CREATE INDEX IF NOT EXISTS idx_mentions_video      ON mentions(video_id);

-- Extraction slice: flag whether a mention came from the transcript or the
-- (lower-trust) description. Idempotent so re-running schema.sql is safe.
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS source TEXT;  -- transcript | description

-- Per-mention note + conviction (idempotent)
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS note TEXT;
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS conviction INT;
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS long_note TEXT;

-- Channel enable/disable flag (source of truth is this table)
ALTER TABLE channels ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT true;
