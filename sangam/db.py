"""Postgres/Supabase access via psycopg 3."""
from __future__ import annotations
from contextlib import contextmanager

import psycopg

from . import config


@contextmanager
def connect():
    if not config.DB_URL:
        raise RuntimeError("SANGAM_DB_URL is not set — put your Supabase connection string in .env")
    conn = psycopg.connect(config.DB_URL, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema():
    ddl = (config.ROOT / "sangam" / "schema.sql").read_text()
    with connect() as conn:
        conn.execute(ddl)


def upsert_channels(conn, channels):
    conn.cursor().executemany(
        """
        INSERT INTO channels (channel_id, name, handle, source_type, is_sebi_registered)
        VALUES (%(channel_id)s, %(name)s, %(handle)s, %(source_type)s, %(is_sebi_registered)s)
        ON CONFLICT (channel_id) DO UPDATE
          SET name = EXCLUDED.name,
              handle = EXCLUDED.handle,
              source_type = EXCLUDED.source_type,
              is_sebi_registered = EXCLUDED.is_sebi_registered
        """,
        channels,
    )


def insert_video_if_new(conn, video: dict) -> bool:
    """Insert a video; returns True if it was new (not already stored)."""
    cur = conn.execute(
        """
        INSERT INTO videos (video_id, channel_id, title, description, url, published_at, is_short)
        VALUES (%(video_id)s, %(channel_id)s, %(title)s, %(description)s, %(url)s, %(published_at)s, %(is_short)s)
        ON CONFLICT (video_id) DO NOTHING
        """,
        video,
    )
    return cur.rowcount == 1


def videos_needing_captions(conn):
    return conn.execute(
        "SELECT video_id, title FROM videos WHERE transcript_status = 'pending' ORDER BY published_at"
    ).fetchall()


def save_transcript(conn, video_id: str, text: str | None, source: str | None, status: str):
    conn.execute(
        "UPDATE videos SET transcript_text=%s, transcript_source=%s, transcript_status=%s WHERE video_id=%s",
        (text, source, status, video_id),
    )


def videos_needing_extract(conn):
    """Pending videos that have something to read: a transcript, or (fallback) a
    description. Returns (video_id, title, transcript_status, transcript_text, description)."""
    return conn.execute(
        """
        SELECT video_id, title, transcript_status, transcript_text, description
        FROM videos
        WHERE extract_status = 'pending'
        ORDER BY published_at
        """
    ).fetchall()


def save_extraction(conn, video_id: str, summary: str | None, status: str):
    conn.execute(
        "UPDATE videos SET summary=%s, extract_status=%s WHERE video_id=%s",
        (summary, status, video_id),
    )


def insert_mentions(conn, video_id: str, rows: list[dict], source: str):
    if not rows:
        return
    conn.cursor().executemany(
        """
        INSERT INTO mentions
          (video_id, raw_mention, resolved_symbol, instrument_type, action, confidence, evidence, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                video_id,
                r.get("raw_mention"),
                r.get("resolved_symbol"),   # None for now (normalization stubbed)
                r.get("instrument_type"),
                r.get("action"),
                r.get("confidence"),
                r.get("evidence"),
                source,
            )
            for r in rows
        ],
    )


def delete_mentions(conn, video_id: str):
    """Clear a video's mentions so re-extraction doesn't duplicate rows."""
    conn.execute("DELETE FROM mentions WHERE video_id = %s", (video_id,))
