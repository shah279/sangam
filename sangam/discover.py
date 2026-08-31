"""Stage 1: poll each channel's long-form (UULF) and shorts (UUSH) feeds, resume
each stream from its stored watermark, tag is_short, and store new items.

The channel list is read FROM Supabase (the `channels` table) — the source of
truth. Add channels via the dashboard or `python3 -m sangam.channels add ...`,
never by editing code. config.CHANNELS is only the one-time seed.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

import feedparser

from . import config, db
from .outcome import StageResult


def _published(entry) -> datetime | None:
    t = getattr(entry, "published_parsed", None)
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


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

    channels = db.get_channels()
    if not channels:
        # First run: seed the table from config, then read it back.
        with db.connect() as conn:
            db.upsert_channels(conn, config.CHANNELS)
        channels = db.get_channels() or config.CHANNELS

    watermarks = {} if lookback_hours is not None else db.discovery_watermarks()
    print(f"discover: {len(channels)} channels")
    for ch in channels:
        for feed_url, is_short in config.feeds_for(ch["channel_id"]):
            stream = (ch["channel_id"], is_short)
            if stream in watermarks:
                cutoff = watermarks[stream] - timedelta(hours=config.DISCOVERY_OVERLAP_HOURS)
            else:
                cutoff = now - timedelta(hours=initial_lookback)
            try:
                feed = feedparser.parse(db.fetch_feed(feed_url))
                if feed.bozo and not feed.entries:
                    raise RuntimeError(str(feed.bozo_exception))
            except Exception as err:
                message = f"feed failed for {ch['name']}: {err}"
                errors.append(message)
                print(f"  ! {message}")
                continue
            for e in feed.entries:
                pub = _published(e)
                if not pub or pub < cutoff:
                    continue
                vid = getattr(e, "yt_videoid", None) or e.get("id", "").split(":")[-1]
                if not vid:
                    continue
                video = {
                    "video_id": vid,
                    "channel_id": ch["channel_id"],
                    "title": e.get("title"),
                    "description": e.get("summary"),
                    "url": e.get("link"),
                    "published_at": pub,
                    "is_short": is_short,
                }
                with db.connect() as conn:
                    if db.insert_video_if_new(conn, video):
                        new_count += 1
                        kind = "short" if is_short else "video"
                        print(f"  + [{kind}] {ch['name']}: {video['title']}")
                processed += 1

    print(f"discover: {new_count} new item(s); {len(errors)} feed error(s)")
    return StageResult("discover", new_count, processed, errors)


if __name__ == "__main__":
    db.init_schema()
    raise SystemExit(0 if discover().ok else 1)
