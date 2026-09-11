"""Supabase access over the REST (PostgREST) API using httpx — pure Python, no
compiled dependencies (works cleanly on Termux). connect() is kept as a no-op
context manager so the other stages don't need changes; the `conn` arg is ignored.
"""
from __future__ import annotations
import atexit
import csv
import io
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
                      "select": "video_id,title,transcript_attempts,transcript_last_error",
                      "order": "published_at",
                  }, timeout=30)
    r.raise_for_status()
    return [(row["video_id"], row["title"], row.get("transcript_attempts") or 0,
             row.get("transcript_last_error"))
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


def mentions_for_normalization() -> list[dict]:
    """Read all mention identities in bounded pages, including existing mappings."""
    rows: list[dict] = []
    page_size = 1000
    start = 0
    while True:
        r = _do(
            "GET",
            _url("mentions"),
            headers=_headers({
                "Range-Unit": "items",
                "Range": f"{start}-{start + page_size - 1}",
            }),
            params={
                "select": "id,raw_mention,resolved_symbol,instrument_type",
                "order": "id",
            },
            timeout=30,
        )
        r.raise_for_status()
        page = r.json()
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def set_mention_normalizations(
    conn, updates: dict[int, tuple[str, str]], chunk_size: int = 100
) -> int:
    """Batch mention updates by canonical symbol/type rather than one request per row."""
    grouped: dict[tuple[str, str], list[int]] = {}
    for mention_id, value in updates.items():
        grouped.setdefault(value, []).append(mention_id)
    changed = 0
    for (symbol, instrument_type), ids in grouped.items():
        for offset in range(0, len(ids), chunk_size):
            chunk = ids[offset:offset + chunk_size]
            r = _do(
                "PATCH",
                _url("mentions"),
                headers=_headers(),
                params={"id": f"in.({','.join(str(value) for value in chunk)})"},
                json={"resolved_symbol": symbol, "instrument_type": instrument_type},
                timeout=30,
            )
            r.raise_for_status()
            changed += len(chunk)
    return changed


def _broker_auth_token() -> str | None:
    """Sign in as Sangam's own dedicated user in the broker project's Supabase
    Auth and return a short-lived JWT. That project's RLS policy is scoped to
    this one authenticated identity (auth.uid()), not to "anon" or to every
    logged-in user of that app — a Sangam-project key/JWT doesn't satisfy it,
    since Supabase Auth identities are per-project. Re-authenticating on every
    call is deliberate: this runs once per pipeline invocation (batch, not a
    long-lived session), so there's no session/refresh-token state worth
    keeping around.
    """
    if not (config.BROKER_SUPABASE_URL and config.BROKER_SUPABASE_ANON_KEY
            and config.BROKER_SUPABASE_EMAIL and config.BROKER_SUPABASE_PASSWORD):
        return None
    r = _do(
        "POST", f"{config.BROKER_SUPABASE_URL}/auth/v1/token",
        headers={"apikey": config.BROKER_SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        params={"grant_type": "password"},
        json={"email": config.BROKER_SUPABASE_EMAIL, "password": config.BROKER_SUPABASE_PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_broker_instruments() -> list[dict]:
    """Read the NSE/BSE equity instrument master from the separate Supabase
    project that already maintains it. Requires signing in as Sangam's
    dedicated service user there (see _broker_auth_token) — that project's RLS
    is scoped to that one identity, so an anon key alone would return nothing.
    The safety of this call depends entirely on that other project's setup,
    not on anything here: its RLS policy must gate on both auth.uid() (who is
    asking) and the row's own owner column (whose data is being exposed —
    a different UID from Sangam's), and its base table's column grants must
    be narrowed to the safe columns so a direct table query can't return
    sensitive ones (token, raw_data, user_id, ...) even if it bypasses the
    sanitized broker_instruments_public view queried below. Returns [] when
    unconfigured or unreachable, so normalize.py degrades to the curated
    alias table alone instead of failing the pipeline.
    """
    token = _broker_auth_token()
    if not token:
        return []
    url = f"{config.BROKER_SUPABASE_URL}/rest/v1/broker_instruments_public"
    base_headers = {"apikey": config.BROKER_SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"}
    rows: list[dict] = []
    page_size = 1000
    start = 0
    while True:
        r = _do(
            "GET", url,
            headers={**base_headers, "Range-Unit": "items",
                     "Range": f"{start}-{start + page_size - 1}"},
            params={"select": "*", "order": "symbol"},
            timeout=30,
        )
        r.raise_for_status()
        page = r.json()
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


NSE_EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_EQUITY_LIST_LOCAL_PATH = config.ROOT / "sangam" / "data" / "EQUITY_L.csv"


def _parse_nse_equity_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    return [
        {"symbol": (row.get("SYMBOL") or "").strip(), "name": (row.get("NAME OF COMPANY") or "").strip()}
        for row in reader
    ]


def fetch_nse_equity_list() -> list[dict]:
    """Read NSE's equity list: symbol + registered company name. Used as a
    normalization fallback for mentions that name a company (not its ticker)
    and aren't in the broker instrument master's ticker-only names either.

    Tries the live URL first (freshest data), then falls back to a bundled
    local copy at NSE_EQUITY_LIST_LOCAL_PATH if that fails — NSE's archive
    subdomain is Akamai-fronted and unreliable from some networks (observed
    hanging/blocked from a non-residential IP; unconfirmed whether Termux's
    mobile IP fares better). The local copy goes stale over time (new IPOs,
    renamed companies) but that's a fine tradeoff against depending entirely
    on a scrape with no SLA. Refresh it occasionally by re-downloading from
    NSE's own site (nseindia.com -> Market Data -> Securities Available for
    Trading -> "Securities available for Equity segment (.csv)") and
    replacing the file — it's a normal browser download, not an API call.
    Returns [] only if neither source is available, so normalize.py can
    degrade to its other sources instead of failing the pipeline.
    """
    try:
        r = fetch_external(NSE_EQUITY_LIST_URL, timeout=30)
        r.raise_for_status()
        return _parse_nse_equity_csv(r.text)
    except httpx.HTTPError:
        pass
    if NSE_EQUITY_LIST_LOCAL_PATH.exists():
        return _parse_nse_equity_csv(NSE_EQUITY_LIST_LOCAL_PATH.read_text(encoding="utf-8"))
    return []


BSE_EQUITY_LIST_LOCAL_PATH = config.ROOT / "sangam" / "data" / "BSE_EQUITY_LIST.csv"


def fetch_bse_equity_list() -> list[dict]:
    """Read BSE's equity list from a manually-downloaded local copy. BSE
    identifies a company two ways that both show up in casual use — the
    alphabetic "Security Id" (e.g. "ABB") and the numeric "Security Code"
    scrip code (e.g. "500002") — so both are returned; callers should index
    a company's name under each. Unlike NSE, no working unauthenticated live
    URL was found for this — BSE's site is a modern SPA whose data API
    blocks cross-origin/automated requests — so this is local-file-only.
    Refresh occasionally by re-downloading from
    bseindia.com/corporates/List_Scrips.aspx (Segment: Equity T+1, Status:
    Active) and replacing the file. Returns [] if the file isn't present, so
    normalize.py degrades gracefully (BSE-only names just won't show).
    """
    if not BSE_EQUITY_LIST_LOCAL_PATH.exists():
        return []
    reader = csv.DictReader(io.StringIO(BSE_EQUITY_LIST_LOCAL_PATH.read_text(encoding="utf-8-sig")))
    return [
        {
            "symbol": (row.get("Security Id") or "").strip(),
            "scrip_code": (row.get("Security Code") or "").strip(),
            "name": (row.get("Issuer Name") or "").strip(),
            "status": (row.get("Status") or "").strip(),
        }
        for row in reader
    ]


def fetch_external(url: str, *, timeout: float = 30, **kwargs) -> httpx.Response:
    """GET a public third-party endpoint (e.g. Yahoo Finance) with the same
    retry/backoff used for Supabase calls. Unlike fetch_feed/fetch_youtube_page,
    this does not raise_for_status itself: a 404 from a price API can mean
    "no data for this ticker" rather than a real error, and callers need to
    tell the two apart. `timeout` is a real parameter (not swept into
    **kwargs) so a caller passing it explicitly doesn't collide with the
    default forwarded to _do()."""
    return _do("GET", url, headers=_UA, timeout=timeout, **kwargs)


def symbols_needing_prices() -> list[str]:
    """Distinct stock symbols worth pricing: every resolved mention, plus
    anything a user has added straight to the watchlist by symbol (which may
    never have been mentioned by a creator at all, so mentions alone
    wouldn't surface it)."""
    symbols: set[str] = set()
    page_size = 1000
    start = 0
    while True:
        r = _do(
            "GET", _url("mentions"),
            headers=_headers({
                "Range-Unit": "items",
                "Range": f"{start}-{start + page_size - 1}",
            }),
            params={
                "select": "resolved_symbol",
                "instrument_type": "eq.stock",
                "resolved_symbol": "not.is.null",
                "order": "id",
            },
            timeout=30,
        )
        r.raise_for_status()
        page = r.json()
        symbols.update(row["resolved_symbol"] for row in page)
        if len(page) < page_size:
            break
        start += page_size

    r = _do("GET", _url("watchlist"), headers=_headers(),
            params={"select": "symbol"}, timeout=30)
    r.raise_for_status()
    symbols.update(row["symbol"] for row in r.json())
    return sorted(symbols)


def upsert_price_points(conn, points: list[dict], chunk_size: int = 500) -> int:
    """Batch-insert EOD closes, merging on the (symbol, price_date) primary key."""
    updated = 0
    for offset in range(0, len(points), chunk_size):
        chunk = points[offset:offset + chunk_size]
        r = _do("POST", _url("price_points"),
                headers=_headers({"Prefer": "resolution=merge-duplicates"}),
                json=chunk, timeout=30)
        r.raise_for_status()
        updated += len(chunk)
    return updated


def upsert_instrument_names(conn, rows: list[dict], chunk_size: int = 500) -> int:
    """Batch-insert symbol -> company name pairs, merging on symbol."""
    updated = 0
    for offset in range(0, len(rows), chunk_size):
        chunk = rows[offset:offset + chunk_size]
        r = _do("POST", _url("instrument_names"),
                headers=_headers({"Prefer": "resolution=merge-duplicates"}),
                json=chunk, timeout=30)
        r.raise_for_status()
        updated += len(chunk)
    return updated


def recent_mentions_for_report(limit: int = 3000) -> list[dict]:
    """Read recent mentions with creator/video context for daily consensus output."""
    rows: list[dict] = []
    page_size = min(1000, limit)
    start = 0
    select = (
        "id,video_id,raw_mention,resolved_symbol,instrument_type,action,conviction,"
        "confidence,note,long_note,evidence,source,"
        "video:videos(title,url,published_at,channel_id,"
        "channel:channels(name,source_type,is_sebi_registered,platform))"
    )
    while len(rows) < limit:
        r = _do(
            "GET",
            _url("mentions"),
            headers=_headers({
                "Range-Unit": "items",
                "Range": f"{start}-{start + page_size - 1}",
            }),
            params={"select": select, "order": "created_at.desc"},
            timeout=30,
        )
        r.raise_for_status()
        page = r.json()
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return rows[:limit]


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
    started_at = datetime.now(timezone.utc).isoformat()
    r = _do("POST", _url("runs"),
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
            params={"on_conflict": "run_key"},
            json={"run_key": run_key, "started_at": started_at, "status": "running"}, timeout=30)
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
