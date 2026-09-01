"""Stage 1: poll each channel's canonical upload feed, resume from its stored
watermark, infer obvious Shorts, and batch-insert new items.

The channel list is read FROM Supabase (the `channels` table) — the source of
truth. Add channels via the dashboard or `python3 -m sangam.channels add ...`,
never by editing code. config.CHANNELS is only the one-time seed.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import quote

import feedparser

from . import config, db
from .outcome import StageResult


def _published(entry) -> datetime | None:
    stored = entry.get("published_at")
    if isinstance(stored, datetime):
        return stored
    t = getattr(entry, "published_parsed", None)
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def _looks_short(entry) -> bool:
    """Best-effort classification; YouTube's combined RSS has no duration field."""
    link = entry.get("link", "") or ""
    text = " ".join((entry.get("title", "") or "", entry.get("summary", "") or ""))
    return "/shorts/" in link.lower() or bool(re.search(r"(?<!\w)#shorts?\b", text, re.I))


def _relative_published(label: str, now: datetime) -> datetime | None:
    """Convert YouTube's relative upload label to a stable-enough discovery time."""
    match = re.search(
        r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", label, re.I
    )
    if not match:
        if re.search(r"\btoday\b", label, re.I):
            return now
        if re.search(r"\byesterday\b", label, re.I):
            return now - timedelta(days=1)
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    seconds = {
        "second": 1,
        "minute": 60,
        "hour": 3600,
        "day": 86400,
        "week": 7 * 86400,
        "month": 30 * 86400,
        "year": 365 * 86400,
    }[unit]
    return now - timedelta(seconds=amount * seconds)


def _initial_data(page: bytes) -> dict:
    text = page.decode("utf-8", errors="replace")
    markers = ("var ytInitialData = ", 'window["ytInitialData"] = ')
    decoder = json.JSONDecoder()
    for marker in markers:
        start = text.find(marker)
        if start < 0:
            continue
        try:
            value, _ = decoder.raw_decode(text[start + len(marker):])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("YouTube uploads page did not contain ytInitialData")


def _video_lockups(value):
    """Yield current YouTube upload-card models without descending into each card."""
    if isinstance(value, dict):
        lockup = value.get("lockupViewModel")
        if isinstance(lockup, dict) and lockup.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
            yield lockup
            return
        for child in value.values():
            yield from _video_lockups(child)
    elif isinstance(value, list):
        for child in value:
            yield from _video_lockups(child)


def _uploads_page_entries(handle: str, now: datetime) -> list[dict]:
    """Read recent long-form upload cards when YouTube's RSS endpoint is down."""
    safe_handle = quote(handle.strip().lstrip("@"), safe="._-")
    page = db.fetch_youtube_page(config.YOUTUBE_VIDEOS_PAGE.format(safe_handle))
    entries: list[dict] = []
    for lockup in _video_lockups(_initial_data(page)):
        video_id = lockup.get("contentId")
        metadata = lockup.get("metadata", {}).get("lockupMetadataViewModel", {})
        title = metadata.get("title", {}).get("content")
        rows = (
            metadata.get("metadata", {})
            .get("contentMetadataViewModel", {})
            .get("metadataRows", [])
        )
        labels = [
            part.get("text", {}).get("content", "")
            for row in rows
            for part in row.get("metadataParts", [])
        ]
        published = next(
            (parsed for label in reversed(labels) if (parsed := _relative_published(label, now))),
            None,
        )
        if video_id and title and published:
            entries.append(
                {
                    "video_id": video_id,
                    "title": title,
                    "summary": None,
                    "link": f"https://www.youtube.com/watch?v={video_id}",
                    "published_at": published,
                    "is_short": False,
                }
            )
    return entries


def discover(lookback_hours: int | None = None) -> StageResult:
    """Discover uploads, resuming from each channel's stored watermark.

    ``lookback_hours`` is primarily a backfill/testing override. On normal runs,
    existing channels resume from their newest stored video with a small overlap;
    new channels use the configured initial lookback.
    """
    initial_lookback = lookback_hours or config.LOOKBACK_HOURS
    now = datetime.now(timezone.utc)
    new_count = 0
    processed = 0
    errors: list[str] = []
    candidates: dict[str, dict] = {}

    channels = db.get_channels()
    if not channels:
        # First run: seed the table from config, then read it back.
        with db.connect() as conn:
            db.upsert_channels(conn, config.CHANNELS)
        channels = db.get_channels() or config.CHANNELS

    watermarks = {} if lookback_hours is not None else db.discovery_watermarks()
    channel_names = {ch["channel_id"]: ch["name"] for ch in channels}
    print(f"discover: {len(channels)} channels")
    for ch in channels:
        if ch["channel_id"] in watermarks:
            cutoff = watermarks[ch["channel_id"]] - timedelta(hours=config.DISCOVERY_OVERLAP_HOURS)
        else:
            cutoff = now - timedelta(hours=initial_lookback)
        for feed_url in config.feeds_for(ch["channel_id"]):
            try:
                feed = feedparser.parse(db.fetch_feed(feed_url))
                if feed.bozo and not feed.entries:
                    raise RuntimeError(str(feed.bozo_exception))
                entries = feed.entries
            except Exception as feed_error:
                try:
                    handle = ch.get("handle")
                    if not handle:
                        raise RuntimeError("channel has no saved handle")
                    entries = _uploads_page_entries(handle, now)
                    print(
                        f"  ~ RSS unavailable for {ch['name']}; "
                        f"used uploads-page fallback ({len(entries)} item(s))"
                    )
                except Exception as fallback_error:
                    message = (
                        f"discovery failed for {ch['name']}: RSS: {feed_error}; "
                        f"fallback: {fallback_error}"
                    )
                    errors.append(message)
                    print(f"  ! {message}")
                    continue
            for e in entries:
                pub = _published(e)
                if not pub or pub < cutoff:
                    continue
                vid = (
                    getattr(e, "yt_videoid", None)
                    or e.get("video_id")
                    or e.get("id", "").split(":")[-1]
                )
                if not vid:
                    continue
                explicit_short = e.get("is_short")
                video = {
                    "video_id": vid,
                    "channel_id": ch["channel_id"],
                    "title": e.get("title"),
                    "description": e.get("summary"),
                    "url": e.get("link"),
                    "published_at": pub,
                    "is_short": (
                        bool(explicit_short) if explicit_short is not None else _looks_short(e)
                    ),
                }
                candidates[vid] = video
                processed += 1

    with db.connect() as conn:
        inserted = db.insert_videos_if_new(conn, list(candidates.values()))
    new_count = len(inserted)
    for video in inserted:
        kind = "short" if video.get("is_short") else "video"
        channel_name = channel_names.get(video.get("channel_id"), video.get("channel_id", "?"))
        print(f"  + [{kind}] {channel_name}: {video.get('title')}")

    print(f"discover: {new_count} new item(s); {len(errors)} feed error(s)")
    return StageResult("discover", new_count, processed, errors)


if __name__ == "__main__":
    db.init_schema()
    raise SystemExit(0 if discover().ok else 1)
