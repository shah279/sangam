"""Stage 1: poll each channel's long-form (UULF) and shorts (UUSH) feeds, keep
videos published within the lookback window, tag is_short, store new ones.

The channel list is read FROM Supabase (the `channels` table) — the source of
truth. Add channels via the dashboard or `python3 -m sangam.channels add ...`,
never by editing code. config.CHANNELS is only the one-time seed.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

import feedparser

from . import config, db


def _published(entry) -> datetime | None:
    t = getattr(entry, "published_parsed", None)
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def discover(lookback_hours: int | None = None) -> int:
    lookback_hours = lookback_hours or config.LOOKBACK_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    new_count = 0

    channels = db.get_channels()
    if not channels:
        # First run: seed the table from config, then read it back.
        with db.connect() as conn:
            db.upsert_channels(conn, config.CHANNELS)
        channels = db.get_channels() or config.CHANNELS

    print(f"discover: {len(channels)} channels")
    for ch in channels:
        for feed_url, is_short in config.feeds_for(ch["channel_id"]):
            try:
                feed = feedparser.parse(db.fetch_feed(feed_url))
            except Exception as err:
                print(f"  ! feed failed for {ch['name']}: {err}")
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

    print(f"discover: {new_count} new item(s) in last {lookback_hours}h")
    return new_count


if __name__ == "__main__":
    db.init_schema()
    discover()
