"""Manage the channel list — the source of truth is the Supabase `channels` table.

    python3 -m sangam.channels list                       # show tracked channels
    python3 -m sangam.channels seed                       # one-time: load config.CHANNELS into the table
    python3 -m sangam.channels add <handle|url> [type] [sebi]

Examples:
    python3 -m sangam.channels add @paisasmart research yes
    python3 -m sangam.channels add https://www.youtube.com/@newchannel/videos educator

'type' is research | educator | opinion (default educator). 'sebi' = yes/no (default no).
Adding a channel needs NO code change — it just inserts a row the pipeline reads next run.
"""
from __future__ import annotations
import re
import sys

import httpx

from . import config, db

_ID = re.compile(r'(UC[0-9A-Za-z_-]{22})')
_UA = {"User-Agent": "Mozilla/5.0 (compatible; SangamBot/1.0)"}


def _handle_from(s: str) -> str:
    s = s.strip().rstrip("/")
    if "youtube.com" in s:
        s = s.split("?")[0]
        for part in s.split("/"):
            if part.startswith("@"):
                return part[1:]
        return s.split("/")[-1]
    return s.lstrip("@")


def resolve(handle_or_url: str) -> tuple[str, str, str]:
    """Return (channel_id, name, handle) by reading the channel's page."""
    handle = _handle_from(handle_or_url)
    url = handle_or_url if "youtube.com" in handle_or_url else f"https://www.youtube.com/@{handle}"
    r = httpx.get(url, headers=_UA, timeout=30, follow_redirects=True)
    r.raise_for_status()
    html = r.text
    m = re.search(r'"(?:channelId|externalId)":"(UC[0-9A-Za-z_-]{22})"', html) or _ID.search(html)
    if not m:
        raise RuntimeError("Could not find a channel id on that page — check the handle/URL.")
    cid = m.group(1)
    nm = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    name = (nm.group(1) if nm else handle).strip()
    return cid, name, handle


def add(handle_or_url: str, source_type: str = "educator", sebi: bool = False):
    cid, name, handle = resolve(handle_or_url)
    ch = {"channel_id": cid, "name": name, "handle": handle,
          "source_type": source_type, "is_sebi_registered": sebi}
    db.upsert_channels(None, [ch])
    print(f"added: {name}  ({cid})  type={source_type}  sebi={sebi}")


def seed():
    db.upsert_channels(None, config.CHANNELS)
    print(f"seeded {len(config.CHANNELS)} channels from config into the table")


def list_channels():
    rows = db.get_channels()
    for c in rows:
        tag = "SEBI" if c.get("is_sebi_registered") else "-"
        print(f"  {c['channel_id']}  {c.get('source_type','?'):9} {tag:4} {c['name']}")
    print(f"{len(rows)} channels")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "seed":
        seed()
    elif cmd == "list":
        list_channels()
    elif cmd == "add":
        if len(sys.argv) < 3:
            print("usage: add <handle|url> [type] [sebi]"); return
        stype = sys.argv[3] if len(sys.argv) > 3 else "educator"
        sebi = len(sys.argv) > 4 and sys.argv[4].lower() in ("yes", "true", "1", "sebi")
        add(sys.argv[2], stype, sebi)
    else:
        print(f"unknown command '{cmd}'. use: list | seed | add")


if __name__ == "__main__":
    main()
