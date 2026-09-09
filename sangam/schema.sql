-- Sangam schema (Postgres / Supabase). Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS channels (
    channel_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    handle              TEXT,
    platform            TEXT NOT NULL DEFAULT 'youtube',
    source_type         TEXT,            -- research | educator | opinion (your tag)
    is_sebi_registered  BOOLEAN,
    active              BOOLEAN NOT NULL DEFAULT true
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
    transcript_status  TEXT DEFAULT 'pending',   -- pending | retry | done | unavailable | error
    transcript_source  TEXT,                      -- captions | whisper (later)
    transcript_text    TEXT,
    transcript_attempts INT NOT NULL DEFAULT 0,
    transcript_last_error TEXT,
    transcript_next_retry_at TIMESTAMPTZ,
    summary            TEXT,                      -- filled by extraction slice
    extract_status     TEXT DEFAULT 'pending',    -- pending | retry | done | skipped | error
    extract_attempts   INT NOT NULL DEFAULT 0,
    extract_last_error TEXT,
    extract_next_retry_at TIMESTAMPTZ
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

CREATE TABLE IF NOT EXISTS runs (
    id            BIGSERIAL PRIMARY KEY,
    run_key       TEXT NOT NULL DEFAULT md5(random()::text || clock_timestamp()::text) UNIQUE,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'running', -- running | success | partial | failed
    new_videos    INT NOT NULL DEFAULT 0,
    transcribed   INT NOT NULL DEFAULT 0,
    mentions      INT NOT NULL DEFAULT 0,
    error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_videos_published    ON videos(published_at);
CREATE INDEX IF NOT EXISTS idx_videos_stream_published ON videos(channel_id, is_short, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_videos_transcript   ON videos(transcript_status);
CREATE INDEX IF NOT EXISTS idx_videos_extract      ON videos(extract_status);
CREATE INDEX IF NOT EXISTS idx_mentions_symbol     ON mentions(resolved_symbol);
CREATE INDEX IF NOT EXISTS idx_mentions_video      ON mentions(video_id);
CREATE INDEX IF NOT EXISTS idx_runs_started         ON runs(started_at DESC);

-- Extraction slice: flag whether a mention came from the transcript or the
-- (lower-trust) description. Idempotent so re-running schema.sql is safe.
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS source TEXT;  -- transcript | description

-- Per-mention note + conviction (idempotent)
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS note TEXT;
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS conviction INT;
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS long_note TEXT;

-- Channel enable/disable flag (source of truth is this table)
ALTER TABLE channels ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT true;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'youtube';
UPDATE channels SET platform = 'youtube' WHERE platform IS NULL;
ALTER TABLE channels ALTER COLUMN platform SET NOT NULL;

-- Retry metadata. These ALTERs upgrade databases created by earlier versions.
ALTER TABLE videos ADD COLUMN IF NOT EXISTS transcript_attempts INT DEFAULT 0;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS transcript_last_error TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS transcript_next_retry_at TIMESTAMPTZ;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS extract_attempts INT DEFAULT 0;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS extract_last_error TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS extract_next_retry_at TIMESTAMPTZ;
UPDATE videos SET transcript_attempts = 0 WHERE transcript_attempts IS NULL;
UPDATE videos SET extract_attempts = 0 WHERE extract_attempts IS NULL;
ALTER TABLE videos ALTER COLUMN transcript_attempts SET NOT NULL;
ALTER TABLE videos ALTER COLUMN extract_attempts SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_videos_transcript_retry ON videos(transcript_next_retry_at);
CREATE INDEX IF NOT EXISTS idx_videos_extract_retry ON videos(extract_next_retry_at);

-- Client-generated idempotency key prevents duplicate run rows after an ambiguous retry.
ALTER TABLE runs ADD COLUMN IF NOT EXISTS run_key TEXT
    DEFAULT md5(random()::text || clock_timestamp()::text);
UPDATE runs SET run_key = md5(random()::text || clock_timestamp()::text) WHERE run_key IS NULL;
ALTER TABLE runs ALTER COLUMN run_key SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_run_key ON runs(run_key);

-- Older deployments allowed null start times and did not preserve the default.
-- Backfill with the best timestamp still available and repair the contract.
ALTER TABLE runs ALTER COLUMN started_at SET DEFAULT now();
UPDATE runs SET started_at = COALESCE(finished_at, now()) WHERE started_at IS NULL;
ALTER TABLE runs ALTER COLUMN started_at SET NOT NULL;

-- One transaction replaces an extraction, so a failed insert cannot erase good mentions.
CREATE OR REPLACE FUNCTION public.replace_video_extraction(
    p_video_id TEXT,
    p_summary TEXT,
    p_source TEXT,
    p_mentions JSONB,
    p_attempts INT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    DELETE FROM public.mentions WHERE video_id = p_video_id;

    INSERT INTO public.mentions (
        video_id, raw_mention, resolved_symbol, instrument_type, action,
        conviction, note, long_note, confidence, evidence, source
    )
    SELECT
        p_video_id, x.raw_mention, x.resolved_symbol, x.instrument_type, x.action,
        x.conviction, x.note, x.long_note, x.confidence, x.evidence, p_source
    FROM jsonb_to_recordset(COALESCE(p_mentions, '[]'::jsonb)) AS x(
        raw_mention TEXT,
        resolved_symbol TEXT,
        instrument_type TEXT,
        action TEXT,
        conviction INT,
        note TEXT,
        long_note TEXT,
        confidence REAL,
        evidence TEXT
    );

    UPDATE public.videos
    SET summary = p_summary,
        extract_status = 'done',
        extract_attempts = p_attempts,
        extract_last_error = NULL,
        extract_next_retry_at = NULL
    WHERE video_id = p_video_id;
END;
$$;

REVOKE ALL ON FUNCTION public.replace_video_extraction(TEXT, TEXT, TEXT, JSONB, INT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.replace_video_extraction(TEXT, TEXT, TEXT, JSONB, INT)
    TO service_role;

-- Exact per-feed cursors prevent one healthy feed from hiding gaps in another feed.
CREATE OR REPLACE FUNCTION public.latest_stream_watermarks()
RETURNS TABLE (channel_id TEXT, is_short BOOLEAN, published_at TIMESTAMPTZ)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT v.channel_id, COALESCE(v.is_short, false), max(v.published_at)
    FROM public.videos AS v
    WHERE v.published_at IS NOT NULL
    GROUP BY v.channel_id, COALESCE(v.is_short, false);
$$;

REVOKE ALL ON FUNCTION public.latest_stream_watermarks() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.latest_stream_watermarks() TO service_role;

-- The app embeds a publishable anon key and is read-only. Keep all writes server-side.
ALTER TABLE public.channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.videos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mentions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.runs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.channels, public.videos, public.mentions, public.runs
    FROM anon, authenticated;
GRANT SELECT ON TABLE public.channels, public.videos, public.mentions, public.runs
    TO anon, authenticated;

DROP POLICY IF EXISTS "public read channels" ON public.channels;
DROP POLICY IF EXISTS "public read videos" ON public.videos;
DROP POLICY IF EXISTS "public read mentions" ON public.mentions;
DROP POLICY IF EXISTS "public read runs" ON public.runs;
CREATE POLICY "public read channels" ON public.channels FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read videos" ON public.videos FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read mentions" ON public.mentions FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read runs" ON public.runs FOR SELECT TO anon, authenticated USING (true);

-- EOD close cache for price-tracking features (radar, creator scorecards).
-- Populated from Yahoo Finance's free chart API since NSE/BSE has no official
-- free EOD feed; symbol matches mentions.resolved_symbol.
CREATE TABLE IF NOT EXISTS price_points (
    symbol      TEXT NOT NULL,
    price_date  DATE NOT NULL,
    close       NUMERIC NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, price_date)
);
CREATE INDEX IF NOT EXISTS idx_price_points_symbol ON price_points(symbol, price_date DESC);

ALTER TABLE public.price_points ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.price_points FROM anon, authenticated;
GRANT SELECT ON TABLE public.price_points TO anon, authenticated;
DROP POLICY IF EXISTS "public read price_points" ON public.price_points;
CREATE POLICY "public read price_points" ON public.price_points FOR SELECT TO anon, authenticated USING (true);

-- One row per symbol's most recent close, so the app can fetch "current price"
-- for a set of symbols without pulling each symbol's full 2-year history.
CREATE OR REPLACE VIEW public.latest_prices AS
SELECT DISTINCT ON (symbol) symbol, price_date, close
FROM public.price_points
ORDER BY symbol, price_date DESC;

ALTER VIEW public.latest_prices SET (security_invoker = true);
GRANT SELECT ON public.latest_prices TO anon, authenticated;

-- Personal watchlist ("radar"): the app captures entry_price itself at the
-- moment a pick is added, so it's a plain snapshot rather than a foreign key
-- into price_points. This is the one table the (single-user, no-login) app
-- writes directly: the anon key may INSERT a pick and DELETE it later, but
-- every other table — and every other operation here — stays read-only.
CREATE TABLE IF NOT EXISTS watchlist (
    id           BIGSERIAL PRIMARY KEY,
    symbol       TEXT NOT NULL,
    added_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    entry_price  NUMERIC,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_watchlist_symbol ON watchlist(symbol);

ALTER TABLE public.watchlist ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.watchlist FROM anon, authenticated;
GRANT SELECT, INSERT, DELETE ON TABLE public.watchlist TO anon, authenticated;
DROP POLICY IF EXISTS "public read watchlist" ON public.watchlist;
DROP POLICY IF EXISTS "public add to watchlist" ON public.watchlist;
DROP POLICY IF EXISTS "public remove from watchlist" ON public.watchlist;
CREATE POLICY "public read watchlist" ON public.watchlist FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public add to watchlist" ON public.watchlist FOR INSERT TO anon, authenticated WITH CHECK (true);
CREATE POLICY "public remove from watchlist" ON public.watchlist FOR DELETE TO anon, authenticated USING (true);
