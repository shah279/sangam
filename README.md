# Sangam

Sangam discovers recent uploads from Indian-finance YouTube channels, fetches the
best Hindi/English caption track, extracts grounded instrument mentions with Gemini,
and stores the results in Supabase. The Compose Multiplatform app is a read-only
viewer for consensus, creators, video summaries, and pipeline health.

## Setup

1. Create a Supabase project.
2. In the Supabase SQL editor, run the complete [`sangam/schema.sql`](sangam/schema.sql)
   file. It is idempotent and contains the tables, retry fields, atomic extraction
   functions, indexes, RLS, and read-only mobile policies.
3. Copy the environment template and fill in the server-side credentials:

   ```bash
   cp env.example.txt .env
   pip3 install -r requirements.txt
   ```

   `SANGAM_SUPABASE_KEY` must be a server-side secret/service-role key. Never put it
   in the mobile app. The app uses its separate publishable anon key and can only
   read because of the policies in `schema.sql`.
4. Verify that the deployed database matches this code:

   ```bash
   python3 -m sangam.ingest init
   ```

   `init` validates the schema; it does not execute SQL remotely.
5. Run the complete pipeline:

   ```bash
   python3 -m sangam.ingest
   ```

## Commands

```bash
python3 -m sangam.ingest discover  # RSS discovery only
python3 -m sangam.ingest captions  # due caption work only
python3 -m sangam.ingest extract   # due Gemini work only
python3 -m sangam.ingest normalize   # backfill reviewed canonical symbols/types
python3 -m sangam.ingest unresolved  # list unresolved stock names worth a curated alias
python3 -m sangam.ingest prices      # fetch/backfill EOD closes for resolved stock symbols
python3 -m sangam.ingest retry       # explicitly requeue terminal/legacy failures
python3 -m sangam.evaluate         # deterministic extraction quality gate
python3 -m sangam.evaluate --live  # optional: re-run fixtures through Gemini
python3 -m sangam.daily            # daily JSON/Markdown/narration/SRT (+ MP4 with ffmpeg)
python3 -m sangam.channels list
python3 -m sangam.channels add @channel_handle research yes
```

The complete pipeline validates the schema before it starts. Individual stage
commands skip that repeated check for faster debugging; run `init` explicitly after
changing `schema.sql` or credentials.

Normal discovery resumes from each channel's most recent stored upload, with an
overlap to avoid boundary gaps. A newly added channel uses `SANGAM_LOOKBACK_HOURS`.
It polls one canonical RSS feed per channel and batch-inserts results. When YouTube's
RSS service returns an error, discovery falls back to the channel's public long-form
uploads page. Recovery is still limited by how many items YouTube exposes in those
sources, so use a larger initial lookback or a separate backfill source after a long
outage.

Caption and extraction outages are stored as `retry` with exponential backoff. After
`SANGAM_MAX_STAGE_ATTEMPTS`, the item moves to `error` and requires the explicit
`retry` command. Videos that genuinely cannot provide captions use `unavailable`, so
description-only extraction can proceed without confusing an outage with absence.
Private and members-only videos are also terminal `unavailable` items rather than
retries.
If YouTube blocks the current host/proxy, the caption stage stops after the first
blocked request instead of repeating it across the backlog; the untouched items stay
pending for a later run.

A complete run writes a `runs` record and exits non-zero when any stage is partial or
failed. This makes systemd and the app's Health screen reflect real failures.

## Phase 2 quality and daily output

Normalization uses a reviewed exact-alias catalog. It merges common company, index,
sector, commodity, and mutual-fund variants while leaving ambiguous names unresolved;
it intentionally does not fuzzy-match financial instruments. Run `normalize` once
after updating the alias catalog to backfill existing mentions. New extractions are
normalized before they are stored.

Consensus excludes description-only and low-confidence mentions. A creator gets one
weighted vote per instrument even when several of their videos repeat the same view.
The app still shows the total mention count for transparency and its Health screen
shows caption/extraction backlog counts alongside run history.

`sangam.daily` writes a dated report package under `SANGAM_REPORT_DIR`: `brief.json`,
`brief.md`, `narration.txt`, and `captions.srt`. If `ffmpeg` and a supported font are
available, it also renders a silent text-first 1080x1920 `brief.mp4`. Narration is
kept as a separate artifact so a preferred voice service can be added without
coupling it to ingestion.

## Caption check

Use a known public video before relying on a new host:

```bash
python3 -c "from sangam.captions import _api, fetch_caption; print(fetch_caption(_api(), 'VIDEO_ID')[:200])"
```

YouTube can block datacenter IPs. If that happens, configure `SANGAM_PROXY_URL`.

## Tests

```bash
PYTHONPYCACHEPREFIX=/tmp/sangam-pycache python3 -m unittest discover -s tests -v
```

Phase 2 is complete. The Instagram design notes for Phase 3 are in
[`docs/instagram-phase3.md`](docs/instagram-phase3.md).
