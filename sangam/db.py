"""Supabase access over the REST (PostgREST) API using httpx — pure Python, no
compiled dependencies (works cleanly on Termux). connect() is kept as a no-op
context manager so the other stages don't need changes; the `conn` arg is ignored.
"""
from __future__ import annotations
import atexit
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import email.utils
import random
import time
import uuid

import httpx

from . import config

# Transient network errors common on a phone (dropped Wi-Fi, DNS hiccup, slow reply).
# httpx.TransportError is the parent of every network-level failure — connect,
# read/write, timeouts, protocol errors, and connection resets ([Errno 104]).
_TRANSIENT = (httpx.TransportError,)
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
_UA = {"User-Agent": "Mozilla/5.0 (compatible; SangamBot/1.0)"}
_CLIENT = httpx.Client()
atexit.register(_CLIENT.close)


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed is None:
                return None
            return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _do(method: str, url: str, *, max_attempts: int = 5, **kwargs):
    """HTTP call with bounded retry for transport errors and transient statuses."""
    delay, last = 2.0, None
    for attempt in range(max_attempts):
        try:
            response = _CLIENT.request(method, url, **kwargs)
        except _TRANSIENT as e:
            last = e
            if attempt == max_attempts - 1:
                break
        else:
            if response.status_code not in _RETRYABLE_STATUS or attempt == max_attempts - 1:
                return response
            last = httpx.HTTPStatusError(
                f"retryable HTTP {response.status_code}", request=response.request, response=response
            )
            retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
            if retry_after is not None:
                delay = retry_after
            response.close()
        time.sleep(min(delay, 60) * random.uniform(0.8, 1.2))
        delay = min(delay * 2, 20)
    raise last


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
    """Verify the checked-in schema contract; schema.sql must be applied separately."""
    checks = {
        "channels": "channel_id,platform,active",
        "videos": (
            "video_id,transcript_status,transcript_attempts,transcript_next_retry_at,"
            "extract_status,extract_attempts,extract_next_retry_at"
        ),
        "mentions": "id,video_id,long_note,conviction,source",
        "runs": "id,run_key,started_at,finished_at,status,new_videos,transcribed,mentions,error",
    }
    try:
        for table, columns in checks.items():
            r = _do("GET", _url(table), headers=_headers(),
                    params={"select": columns, "limit": 0}, timeout=30)
            r.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            "Supabase credentials failed or the schema is outdated. Apply "
            "sangam/schema.sql in the Supabase SQL editor, verify the server-side "
            "URL/key, then run `python3 -m sangam.ingest init` again. "
            f"Details: {e}"
        ) from e
    print("Supabase reachable; schema contract OK.")


def upsert_channels(conn, channels):
    body = [
        {
            **{k: c[k] for k in ("channel_id", "name", "handle", "source_type", "is_sebi_registered")},
            "platform": c.get("platform", "youtube"),
            "active": c.get("active", True),
        }
        for c in channels
    ]
    r = _do("POST", _url("channels"), headers=_headers({"Prefer": "resolution=merge-duplicates"}),
                   json=body, timeout=30)
    r.raise_for_status()


def insert_videos_if_new(conn, videos: list[dict]) -> list[dict]:
    """Insert a discovery batch and return only rows that were newly created."""
    if not videos:
        return []
    payload = [{k: _jsonable(v) for k, v in video.items()} for video in videos]
    r = _do("POST", 
        _url("videos"),
        headers=_headers({"Prefer": "resolution=ignore-duplicates,return=representation"}),
        json=payload, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def videos_needing_captions(conn):
    now = datetime.now(timezone.utc).isoformat()
    r = _do("GET", _url("videos"), headers=_headers(),
                  params={
                      "and": (
                          "(or(transcript_status.eq.pending,transcript_status.eq.retry),"
                          f"or(transcript_next_retry_at.is.null,transcript_next_retry_at.lte.{now}))"
                      ),
                      "select": "video_id,title,transcript_attempts",
                      "order": "published_at",
                  }, timeout=30)
    r.raise_for_status()
    return [(row["video_id"], row["title"], row.get("transcript_attempts") or 0)
            for row in r.json()]


def save_transcript(conn, video_id, text, source, status, *, attempts=None,
                    error=None, next_retry_at=None):
    body = {"transcript_text": text, "transcript_source": source,
            "transcript_status": status, "transcript_last_error": error,
            "transcript_next_retry_at": next_retry_at}
    if attempts is not None:
        body["transcript_attempts"] = attempts
    r = _do("PATCH", _url("videos"), headers=_headers(), params={"video_id": f"eq.{video_id}"},
                    json=body, timeout=30)
    r.raise_for_status()


def videos_needing_extract(conn):
    now = datetime.now(timezone.utc).isoformat()
    r = _do("GET", _url("videos"), headers=_headers(),
                  params={
                      "and": (
                          "(or(extract_status.eq.pending,extract_status.eq.retry),"
                          f"or(extract_next_retry_at.is.null,extract_next_retry_at.lte.{now}))"
                      ),
                      "transcript_status": "in.(done,unavailable,none,error)",
                      "select": (
                          "video_id,title,transcript_status,transcript_text,description,extract_attempts"
                      ),
                      "order": "published_at",
                  }, timeout=30)
    r.raise_for_status()
    return [(x["video_id"], x["title"], x["transcript_status"], x["transcript_text"],
             x["description"], x.get("extract_attempts") or 0)
            for x in r.json()]


def save_extraction(conn, video_id, summary, status, *, attempts=None,
                    error=None, next_retry_at=None):
    body = {"summary": summary, "extract_status": status,
            "extract_last_error": error, "extract_next_retry_at": next_retry_at}
    if attempts is not None:
        body["extract_attempts"] = attempts
    r = _do("PATCH", _url("videos"), headers=_headers(), params={"video_id": f"eq.{video_id}"},
                    json=body, timeout=30)
    r.raise_for_status()


def replace_extraction(conn, video_id, summary, rows, source, attempts):
    """Atomically replace mentions and mark extraction done through a SQL RPC."""
    payload = {
        "p_video_id": video_id,
        "p_summary": summary,
        "p_source": source,
        "p_mentions": rows,
        "p_attempts": attempts,
    }
    r = _do("POST", f"{config.SUPABASE_URL}/rest/v1/rpc/replace_video_extraction",
            headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()


def get_channels(conn=None):
    """Read active channels from Supabase, the pipeline's source of truth."""
    base = {
        "select": "channel_id,name,handle,platform,source_type,is_sebi_registered,active",
        "order": "name",
    }
    r = _do("GET", _url("channels"), headers=_headers(),
            params={**base, "active": "eq.true"}, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_feed(url: str) -> bytes:
    """Fetch an RSS feed with the same retry/backoff as everything else, so a
    dropped connection on a feed doesn't crash discovery. Feed failures fall back
    to the uploads page, so do not spend the full database retry budget here."""
    r = _do("GET", url, headers=_UA, timeout=30, max_attempts=1)
    r.raise_for_status()
    return r.content


def fetch_youtube_page(url: str) -> bytes:
    """Fetch a public YouTube page for the RSS discovery fallback."""
    r = _do(
        "GET", url, headers=_UA, timeout=30, follow_redirects=True, max_attempts=2
    )
    r.raise_for_status()
    return r.content


def discovery_watermarks() -> dict[str, datetime]:
    """Return the latest stored publish time per channel."""
    r = _do("POST", f"{config.SUPABASE_URL}/rest/v1/rpc/latest_stream_watermarks",
            headers=_headers(), json={}, timeout=30)
    r.raise_for_status()
    latest: dict[str, datetime] = {}
    for row in r.json():
        raw = row.get("published_at")
        if not raw:
            continue
        published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        channel_id = row["channel_id"]
        if channel_id not in latest or published > latest[channel_id]:
            latest[channel_id] = published
    return latest


def retry_at(attempt: int) -> str:
    minutes = min(config.RETRY_BASE_MINUTES * (2 ** max(0, attempt - 1)), 6 * 60)
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def start_run() -> int:
    run_key = str(uuid.uuid4())
    r = _do("POST", _url("runs"),
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
            params={"on_conflict": "run_key"},
            json={"run_key": run_key, "status": "running"}, timeout=30)
    r.raise_for_status()
    return int(r.json()[0]["id"])


def finish_run(run_id: int, status: str, *, new_videos=0, transcribed=0,
               mentions=0, error=None):
    r = _do("PATCH", _url("runs"), headers=_headers(), params={"id": f"eq.{run_id}"},
            json={"finished_at": datetime.now(timezone.utc).isoformat(), "status": status,
                  "new_videos": new_videos, "transcribed": transcribed,
                  "mentions": mentions, "error": error}, timeout=30)
    r.raise_for_status()


def requeue_failed() -> tuple[int, int]:
    """Explicitly requeue terminal failures, including legacy ``none`` captions."""
    headers = _headers({"Prefer": "return=representation"})
    captions_response = _do(
        "PATCH",
        _url("videos"),
        headers=headers,
        params={"transcript_status": "in.(none,error)"},
        json={
            "transcript_status": "pending",
            "transcript_attempts": 0,
            "transcript_last_error": None,
            "transcript_next_retry_at": None,
            # A previous description-only extraction must be replaced if captions recover.
            "extract_status": "pending",
            "extract_attempts": 0,
            "extract_last_error": None,
            "extract_next_retry_at": None,
        },
        timeout=30,
    )
    captions_response.raise_for_status()

    extract_response = _do(
        "PATCH",
        _url("videos"),
        headers=headers,
        params={"extract_status": "eq.error"},
        json={
            "extract_status": "pending",
            "extract_attempts": 0,
            "extract_last_error": None,
            "extract_next_retry_at": None,
        },
        timeout=30,
    )
    extract_response.raise_for_status()
    return len(captions_response.json()), len(extract_response.json())
