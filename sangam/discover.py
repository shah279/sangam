"""Stage 1: poll each channel's long-form (UULF) and shorts (UUSH) feeds, keep
videos published within the lookback window, tag is_short, store new ones."""
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

    with db.connect() as conn:
        db.upsert_channels(conn, config.CHANNELS)
        for ch in config.CHANNELS:
            for feed_url, is_short in config.feeds_for(ch["channel_id"]):
                feed = feedparser.parse(feed_url)
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
                        "description": e.get("summary"),  # RSS media:description (may be truncated)
                        "url": e.get("link"),
                        "published_at": pub,
                        "is_short": is_short,
                    }
                    if db.insert_video_if_new(conn, video):
                        new_count += 1
                        kind = "short" if is_short else "video"
                        print(f"  + [{kind}] {ch['name']}: {video['title']}")

    print(f"discover: {new_count} new item(s) in last {lookback_hours}h")
    return new_count


if __name__ == "__main__":
    db.init_schema()
    discover()
