"""Supabase access over the REST (PostgREST) API using httpx — pure Python, no
compiled dependencies (works cleanly on Termux). connect() is kept as a no-op
context manager so the other stages don't need changes; the `conn` arg is ignored.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime

import httpx

from . import config


def _headers(extra: dict | None = None) -> dict:
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError("SANGAM_SUPABASE_URL / SANGAM_SUPABASE_KEY not set in .env")
    h = {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _url(table: str) -> str:
    return f"{config.SUPABASE_URL}/rest/v1/{table}"


def _jsonable(v):
    return v.isoformat() if isinstance(v, datetime) else v


@contextmanager
def connect():
    # No persistent connection with REST; yield None so callers' `with` blocks work.
    yield None


def init_schema():
    """Tables are created once via schema.sql in the Supabase SQL editor. Here we
    just verify connectivity and that the tables exist."""
    try:
        r = httpx.get(_url("channels"), headers=_headers(), params={"limit": 1}, timeout=30)
        if r.status_code == 404:
            print("Tables missing — run schema.sql in the Supabase SQL editor first.")
        else:
            r.raise_for_status()
            print("Supabase reachable; schema OK.")
    except Exception as e:
        print(f"Supabase check failed: {e}")
        raise


def upsert_channels(conn, channels):
    body = [
        {k: c[k] for k in ("channel_id", "name", "handle", "source_type", "is_sebi_registered")}
        for c in channels
    ]
    r = httpx.post(_url("channels"), headers=_headers({"Prefer": "resolution=merge-duplicates"}),
                   json=body, timeout=30)
    r.raise_for_status()


def insert_video_if_new(conn, video: dict) -> bool:
    payload = {k: _jsonable(v) for k, v in video.items()}
    r = httpx.post(
        _url("videos"),
        headers=_headers({"Prefer": "resolution=ignore-duplicates,return=representation"}),
        json=payload, timeout=30,
    )
    r.raise_for_status()
    return len(r.json()) == 1   # rows actually inserted (empty if it was a duplicate)


def videos_needing_captions(conn):
    r = httpx.get(_url("videos"), headers=_headers(),
                  params={"transcript_status": "eq.pending", "select": "video_id,title",
                          "order": "published_at"}, timeout=30)
    r.raise_for_status()
    return [(row["video_id"], row["title"]) for row in r.json()]


def save_transcript(conn, video_id, text, source, status):
    r = httpx.patch(_url("videos"), headers=_headers(), params={"video_id": f"eq.{video_id}"},
                    json={"transcript_text": text, "transcript_source": source,
                          "transcript_status": status}, timeout=30)
    r.raise_for_status()


def videos_needing_extract(conn):
    r = httpx.get(_url("videos"), headers=_headers(),
                  params={"extract_status": "eq.pending",
                          "select": "video_id,title,transcript_status,transcript_text,description",
                          "order": "published_at"}, timeout=30)
    r.raise_for_status()
    return [(x["video_id"], x["title"], x["transcript_status"], x["transcript_text"], x["description"])
            for x in r.json()]


def save_extraction(conn, video_id, summary, status):
    r = httpx.patch(_url("videos"), headers=_headers(), params={"video_id": f"eq.{video_id}"},
                    json={"summary": summary, "extract_status": status}, timeout=30)
    r.raise_for_status()


def insert_mentions(conn, video_id, rows, source):
    if not rows:
        return
    body = [{
        "video_id": video_id,
        "raw_mention": r.get("raw_mention"),
        "resolved_symbol": r.get("resolved_symbol"),
        "instrument_type": r.get("instrument_type"),
        "action": r.get("action"),
        "conviction": r.get("conviction"),
        "note": r.get("note"),
        "confidence": r.get("confidence"),
        "evidence": r.get("evidence"),
        "source": source,
    } for r in rows]
    resp = httpx.post(_url("mentions"), headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()


def delete_mentions(conn, video_id):
    r = httpx.delete(_url("mentions"), headers=_headers(), params={"video_id": f"eq.{video_id}"}, timeout=30)
    r.raise_for_status()
