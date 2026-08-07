# Sangam — ingest slice

Tracks 12 Indian finance YouTube channels. This first slice does **discover → captions →
Supabase**: it polls each channel's long-form (UULF) and shorts (UUSH) RSS feeds, keeps
videos from the last 24h, tags `is_short`, and stores each with its captions transcript.
Extraction (Gemini) and the report come next.

## Setup

1. **Supabase**: create a project, open Project Settings → Database → Connection string,
   copy the pooler URL.
2. **Env**: `cp env.example.txt .env` and fill `SANGAM_DB_URL`. (`.env` is gitignored.)
3. **Install**: `pip3 install -r requirements.txt`
4. **Run**:
   ```bash
   python3 -m sangam.ingest init       # create the tables (runs schema.sql)
   python3 -m sangam.ingest            # discover + captions
   ```
   Or run stages separately: `... ingest discover` / `... ingest captions`.

The `init` step also runs on every full run, so the tables self-create on first use.

## Day-one check (do this first)

Captions from a datacenter IP can be throttled by YouTube. Test one video before
trusting the pipeline:
```bash
python -c "from sangam.captions import _api, fetch_caption; print(fetch_caption(_api(),'A_KNOWN_VIDEO_ID')[:200])"
```
If it returns text, you're clear. If it returns nothing on a video you *know* has
captions, set `SANGAM_PROXY_URL` in `.env` to a proxy — no code change needed.

## Notes

- `source_type` and `is_sebi_registered` in `config.py` are rough guesses from channel
  descriptions — edit to your judgment. They only feed later weighting.
- RSS `description` is often truncated; that's fine for MVP. Full text needs the Data API later.
- Scheduling: run `discover`+`captions` on a systemd timer in the evening (post-market);
  the extraction/report slice runs next morning.

## Next slice

Extraction: transcript → Gemini 3.1 Flash-Lite → `mentions` rows + a `summary` field,
then aggregate + Excel report.
